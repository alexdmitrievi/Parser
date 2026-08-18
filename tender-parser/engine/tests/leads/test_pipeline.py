"""Тесты пайплайна: устойчивость к блокировкам и корректность двух шагов."""

from __future__ import annotations

import pytest

from engine.fetchers.polite_fetcher import PoliteResponse, SourceBlocked
from engine.sources.leads.base import LeadsSourceAdapter, SourceUnavailable
from engine.types import RateLimitConfig, SourceCategory, SourceConfig
from leads.models import LeadCompany, LeadEmail
from leads.pipeline import LeadsPipeline
from leads.storage.sqlite_repo import SqliteLeadsRepository


def make_config(source_id: str) -> SourceConfig:
    return SourceConfig(
        source_id=source_id,
        platform_name=source_id,
        category=SourceCategory.LEADS,
        base_url="https://example.cn",
        rate_limit=RateLimitConfig(min_delay=0.0, max_delay=0.0),
    )


class StubAdapter(LeadsSourceAdapter):
    """Адаптер, который отдаёт заданный результат без сети."""

    def __init__(self, source_id: str, companies=None, blocked=False, unavailable="", **kwargs):
        super().__init__(make_config(source_id), user_agent="TestBot/1.0", **kwargs)
        self._companies = companies or []
        self._blocked = blocked
        self._unavailable = unavailable

    def availability(self):
        return (False, self._unavailable) if self._unavailable else (True, "")

    def collect(self):
        self.ensure_available()
        if self._blocked:
            self.blocked = True
            self.blocked_reason = "HTTP 403 — access refused"
            return []
        return list(self._companies)

    def __exit__(self, *exc):
        return None


@pytest.fixture
def repo(tmp_path):
    repository = SqliteLeadsRepository(str(tmp_path / "leads.sqlite3"))
    repository.migrate()
    yield repository
    repository.close()


@pytest.fixture
def pipeline(repo, profile_config):
    return LeadsPipeline(repo, profile_config)


def sample_company(domain="hongyun-carbon.cn", **kwargs) -> LeadCompany:
    defaults = dict(
        company_name_en="Hongyun Carbon Co., Ltd.",
        domain=domain,
        website=f"https://{domain}",
        province="Shandong",
        profile="petcoke_anode",
        source_name="made_in_china",
    )
    defaults.update(kwargs)
    return LeadCompany(**defaults)


class TestCollectResilience:
    def test_blocked_source_does_not_stop_the_run(self, pipeline, repo, monkeypatch):
        """Требование: заблокировали — пометить, залогировать, продолжить."""
        import leads.pipeline as module

        monkeypatch.setattr(module, "CATALOG_FACTORIES", {
            "blocked_one": lambda **kw: StubAdapter("blocked_one", blocked=True),
            "working_one": lambda **kw: StubAdapter("working_one", companies=[sample_company()]),
        })

        result = pipeline.collect("petcoke_anode")

        by_id = {o.source_id: o for o in result.sources}
        assert by_id["blocked_one"].status == "blocked"
        assert by_id["working_one"].status == "ok"
        assert result.inserted == 1
        assert len(repo.iter_companies()) == 1

    def test_source_requiring_subscription_is_skipped_without_error(self, pipeline, monkeypatch):
        import leads.pipeline as module

        monkeypatch.setattr(module, "CATALOG_FACTORIES", {
            "customs_api": lambda **kw: StubAdapter("customs_api", unavailable="требует подписки"),
        })

        result = pipeline.collect("petcoke_anode")
        assert result.sources[0].status == "unavailable"
        assert "подписки" in result.sources[0].note

    def test_crashing_source_is_contained(self, pipeline, monkeypatch):
        import leads.pipeline as module

        class Exploding(StubAdapter):
            def collect(self):
                raise RuntimeError("парсер сломался")

        monkeypatch.setattr(module, "CATALOG_FACTORIES", {
            "boom": lambda **kw: Exploding("boom"),
            "fine": lambda **kw: StubAdapter("fine", companies=[sample_company()]),
        })

        result = pipeline.collect("petcoke_anode")
        by_id = {o.source_id: o for o in result.sources}
        assert by_id["boom"].status == "error"
        assert by_id["fine"].status == "ok"
        assert result.inserted == 1

    def test_run_fails_only_when_every_source_fails(self, pipeline, monkeypatch):
        import leads.pipeline as module

        monkeypatch.setattr(module, "CATALOG_FACTORIES", {
            "a": lambda **kw: StubAdapter("a", blocked=True),
            "b": lambda **kw: StubAdapter("b", blocked=True),
        })
        assert pipeline.collect("petcoke_anode").status == "failed"


class TestCollectIdempotency:
    def test_second_run_creates_no_duplicates(self, pipeline, repo, monkeypatch):
        """Приёмочный критерий: повторный запуск не создаёт дублей."""
        import leads.pipeline as module

        monkeypatch.setattr(module, "CATALOG_FACTORIES", {
            "cat": lambda **kw: StubAdapter("cat", companies=[sample_company()]),
        })

        first = pipeline.collect("petcoke_anode")
        second = pipeline.collect("petcoke_anode")

        assert (first.inserted, first.updated) == (1, 0)
        assert (second.inserted, second.updated) == (0, 1)
        assert len(repo.iter_companies()) == 1

    def test_same_company_from_two_catalogs_is_one_record(self, pipeline, repo, monkeypatch):
        import leads.pipeline as module

        monkeypatch.setattr(module, "CATALOG_FACTORIES", {
            "a": lambda **kw: StubAdapter("a", companies=[sample_company()]),
            "b": lambda **kw: StubAdapter(
                "b", companies=[sample_company(city="Zibo", source_name="customs_api")]
            ),
        })

        result = pipeline.collect("petcoke_anode")
        assert result.found == 2
        assert len(repo.iter_companies()) == 1
        assert repo.iter_companies()[0].city == "Zibo"  # данные слиты


class TestSeedFile:
    def test_seed_domains_become_companies(self, pipeline, repo):
        result = pipeline.collect(
            "petcoke_anode", sources=[], seed_domains=["hongyun-carbon.cn", "kaifeng-anode.cn"]
        )
        assert result.inserted == 2
        assert {c.domain for c in repo.iter_companies()} == {
            "hongyun-carbon.cn",
            "kaifeng-anode.cn",
        }
        assert all(c.source_name == "seed_file" for c in repo.iter_companies())

    def test_aggregator_domains_are_rejected(self, pipeline, repo):
        pipeline.collect("petcoke_anode", sources=[], seed_domains=["made-in-china.com", "163.com"])
        assert repo.iter_companies() == []

    def test_unparseable_lines_are_skipped(self, pipeline, repo):
        pipeline.collect("petcoke_anode", sources=[], seed_domains=["not a domain", "ok-company.cn"])
        assert [c.domain for c in repo.iter_companies()] == ["ok-company.cn"]


class TestEnrich:
    def test_only_pending_companies_with_a_domain_are_visited(self, pipeline, repo, monkeypatch):
        repo.upsert_companies([
            sample_company(domain="a.cn", enrich_status="pending"),
            sample_company(domain="b.cn", enrich_status="done"),
            LeadCompany(company_name_en="No Site", province="Henan", enrich_status="no_site",
                        profile="petcoke_anode"),
        ])

        visited = []

        class Recorder:
            def enrich(self, company):
                visited.append(company.domain)
                company.enrich_status = "done"
                company.emails.append(LeadEmail(email=f"sales@{company.domain}"))
                return company

            _polite = type("X", (), {"close": lambda self: None})()

        monkeypatch.setattr(
            "leads.pipeline.get_company_site_adapter", lambda **kw: Recorder()
        )

        result = pipeline.enrich()
        assert visited == ["a.cn"]
        assert result.enriched == 1
        assert result.emails_added == 1

    def test_robots_skips_are_reported(self, pipeline, repo, monkeypatch):
        """Приёмочный критерий: в логе видно, какие домены пропущены по robots.txt."""
        repo.upsert_companies([sample_company(domain="a.cn", enrich_status="pending")])

        class Skipper:
            def enrich(self, company):
                company.enrich_status = "skipped_robots"
                company.enrich_note = "disallowed by robots.txt"
                return company

            _polite = type("X", (), {"close": lambda self: None})()

        monkeypatch.setattr("leads.pipeline.get_company_site_adapter", lambda **kw: Skipper())

        result = pipeline.enrich()
        assert result.sources[0].skipped_by_robots == 1
        assert repo.iter_companies()[0].enrich_status == "skipped_robots"

    def test_failure_on_one_domain_does_not_stop_the_rest(self, pipeline, repo, monkeypatch):
        repo.upsert_companies([
            sample_company(domain="a.cn", enrich_status="pending"),
            sample_company(domain="b.cn", enrich_status="pending"),
        ])

        class Flaky:
            def enrich(self, company):
                if company.domain == "a.cn":
                    raise SourceBlocked("https://a.cn", "captcha", 403)
                company.enrich_status = "done"
                return company

            _polite = type("X", (), {"close": lambda self: None})()

        monkeypatch.setattr("leads.pipeline.get_company_site_adapter", lambda **kw: Flaky())

        result = pipeline.enrich()
        assert result.enriched == 1
        statuses = {c.domain: c.enrich_status for c in repo.iter_companies()}
        assert statuses == {"a.cn": "blocked", "b.cn": "done"}

    def test_nothing_to_do_is_not_an_error(self, pipeline):
        result = pipeline.enrich()
        assert result.found == 0
        assert result.status == "success"


class TestUnknownProfile:
    def test_unknown_profile_raises_with_available_names(self, pipeline):
        from leads.profiles import ProfileError

        with pytest.raises(ProfileError, match="petcoke_anode"):
            pipeline.collect("no_such_profile")


class TestAdapterContract:
    def test_leads_adapter_rejects_tender_parse_listing(self):
        adapter = StubAdapter("x")
        with pytest.raises(NotImplementedError, match="parse_companies"):
            adapter.parse_listing(PoliteResponse(url="https://x.cn", status_code=200))

    def test_unavailable_adapter_raises_source_unavailable(self):
        adapter = StubAdapter("x", unavailable="нет ключа")
        with pytest.raises(SourceUnavailable, match="нет ключа"):
            adapter.collect()
