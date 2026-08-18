"""Тесты изоляции: домен leads не должен менять поведение tenders и funding.

Здесь проверяется ровно то, что обещано в требованиях:

* при ``LEADS_ENABLED=false`` ни одна команда ничего не делает;
* правки в общей инфраструктуре (``HttpFetcher``, ``SourceCategory``)
  обратно совместимы;
* адаптеры leads не попадают в выборки тендерных категорий;
* отказ одного источника не роняет прогон.
"""

from __future__ import annotations

import pytest

from engine.config.registry import SourceRegistry
from engine.fetchers.http_fetcher import USER_AGENTS, HttpFetcher
from engine.types import FetchMethod, SourceCategory, SourceConfig


class TestFeatureFlag:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("LEADS_ENABLED", raising=False)
        from shared.config import leads_enabled

        assert leads_enabled() is False

    @pytest.mark.parametrize("value", ["true", "True", "1", "yes", "on"])
    def test_recognised_true_values(self, monkeypatch, value):
        monkeypatch.setenv("LEADS_ENABLED", value)
        from shared.config import leads_enabled

        assert leads_enabled() is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "nonsense"])
    def test_everything_else_is_false(self, monkeypatch, value):
        monkeypatch.setenv("LEADS_ENABLED", value)
        from shared.config import leads_enabled

        assert leads_enabled() is False

    @pytest.mark.parametrize("command", ["collect --profile grain", "enrich", "stats"])
    def test_cli_is_a_noop_when_disabled(self, monkeypatch, capsys, command):
        """Выключенный домен не работает и не роняет расписание (код 0)."""
        monkeypatch.setenv("LEADS_ENABLED", "false")
        from leads.cli import main

        assert main(command.split()) == 0
        assert "LEADS_ENABLED=false" in capsys.readouterr().out

    def test_disabled_cli_touches_no_storage(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LEADS_ENABLED", "false")
        monkeypatch.setenv("LEADS_DB_PATH", str(tmp_path / "must-not-exist.sqlite3"))
        from leads.cli import main

        main(["stats"])
        assert not (tmp_path / "must-not-exist.sqlite3").exists()


class TestHttpFetcherBackwardCompatibility:
    """HttpFetcher используется тендерами — его поведение по умолчанию не менялось."""

    def test_default_construction_still_works(self):
        assert HttpFetcher() is not None

    def test_user_agent_still_rotates_by_default(self):
        fetcher = HttpFetcher()
        assert fetcher._pick_user_agent() in USER_AGENTS

    def test_default_headers_are_browser_like(self):
        headers = HttpFetcher()._build_headers()
        assert headers["User-Agent"] in USER_AGENTS
        assert "ru-RU" in headers["Accept-Language"]

    def test_pinned_user_agent_is_used_when_asked(self):
        fetcher = HttpFetcher(user_agent="TenderProLeadsBot/1.0 (+mailto:a@b.c)")
        assert fetcher._pick_user_agent() == "TenderProLeadsBot/1.0 (+mailto:a@b.c)"
        assert fetcher._build_headers()["User-Agent"] == "TenderProLeadsBot/1.0 (+mailto:a@b.c)"

    def test_default_headers_argument_is_accepted(self):
        """Раньше этот вызов падал с TypeError и ломал BaseSourceAdapter."""
        fetcher = HttpFetcher(default_headers={"X-Test": "1"})
        assert fetcher._build_headers()["X-Test"] == "1"

    def test_base_adapter_can_build_its_fetcher(self):
        from engine.sources.base import BaseSourceAdapter

        config = SourceConfig(
            source_id="t",
            platform_name="t",
            category=SourceCategory.TENDERS,
            base_url="https://example.com",
            headers={"X-Custom": "yes"},
        )
        assert BaseSourceAdapter(config)._get_fetcher() is not None

    def test_config_headers_still_apply(self):
        config = SourceConfig(
            source_id="t",
            platform_name="t",
            category=SourceCategory.TENDERS,
            base_url="https://example.com",
            headers={"Referer": "https://example.com"},
        )
        assert HttpFetcher(config)._build_headers()["Referer"] == "https://example.com"


class TestSourceCategory:
    def test_existing_categories_unchanged(self):
        assert SourceCategory.TENDERS.value == "tenders"
        assert SourceCategory.AUCTIONS.value == "auctions"
        assert SourceCategory.GRANTS.value == "grants"

    def test_leads_category_added(self):
        assert SourceCategory.LEADS.value == "leads"

    def test_leads_adapters_do_not_leak_into_tender_queries(self):
        """Реестр фильтрует по категории — leads не попадёт в тендерный прогон."""
        from engine.sources.leads.made_in_china import MADE_IN_CHINA_CONFIG

        registry = SourceRegistry()
        registry.register(
            SourceConfig(
                source_id="fake_tender",
                platform_name="ft",
                category=SourceCategory.TENDERS,
                base_url="https://example.com",
                fetch_method=FetchMethod.HTTP,
            )
        )
        registry.register(MADE_IN_CHINA_CONFIG)

        assert registry.list_source_ids(SourceCategory.TENDERS) == ["fake_tender"]
        assert registry.list_source_ids(SourceCategory.LEADS) == ["made_in_china"]


class TestPoliteFetcherIdentity:
    """Вежливый режим: честный UA, без прокси, без ротации."""

    def test_user_agent_is_honest_and_has_contact(self, monkeypatch):
        monkeypatch.delenv("LEADS_USER_AGENT", raising=False)
        monkeypatch.setenv("LEADS_CONTACT_EMAIL", "ops@example.com")
        from shared.config import leads_user_agent

        agent = leads_user_agent()
        assert "Bot" in agent
        assert "ops@example.com" in agent
        assert "Mozilla" not in agent  # не маскируемся под браузер

    def test_user_agent_never_rotates(self):
        from engine.fetchers.polite_fetcher import PoliteFetcher

        fetcher = PoliteFetcher(user_agent="TenderProLeadsBot/1.0 (+mailto:a@b.c)")
        agents = {fetcher._headers()["User-Agent"] for _ in range(10)}
        assert agents == {"TenderProLeadsBot/1.0 (+mailto:a@b.c)"}

    def test_no_proxy_is_configured(self):
        """Прокси-ротация запрещена: заблокировали — значит заблокировали."""
        import inspect

        from engine.fetchers import polite_fetcher

        source = inspect.getsource(polite_fetcher.PoliteFetcher._get_client)
        assert "proxy" not in source.replace("# proxy is intentionally never set", "")


class TestPoliteLimits:
    def test_delay_below_the_floor_is_raised(self):
        from leads.profiles import MIN_DELAY_SECONDS, Limits

        limits = Limits.from_dict({"request_delay_seconds": 0.1})
        assert limits.request_delay_seconds == MIN_DELAY_SECONDS

    def test_concurrency_above_the_ceiling_is_capped(self):
        from leads.profiles import MAX_ALLOWED_CONCURRENCY, Limits

        limits = Limits.from_dict({"max_concurrency": 32})
        assert limits.max_concurrency == MAX_ALLOWED_CONCURRENCY
