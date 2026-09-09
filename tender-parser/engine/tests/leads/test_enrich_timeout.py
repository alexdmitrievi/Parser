"""Тесты бюджета времени обогащения: Limits + остановка по таймауту."""

from __future__ import annotations

import time

from engine.fetchers.polite_fetcher import PoliteResponse
from engine.sources.leads.company_site import (
    COMPANY_SITE_CONFIG,
    CompanySiteAdapter,
)
from leads.models import LeadCompany
from leads.profiles import Limits


class _FakeFetcher:
    """Фетчер: спит ``delay`` секунд и отдаёт заданный статус."""

    user_agent = "TestBot/1.0"

    def __init__(self, delay: float, calls: list[str], status_code: int = 200):
        self._delay = delay
        self._calls = calls
        self._status = status_code

    def fetch(self, url: str, **kwargs) -> PoliteResponse:
        self._calls.append(url)
        time.sleep(self._delay)
        return PoliteResponse(
            url=url,
            status_code=self._status,
            text='<html><body><a href="/contact">Contact</a></body></html>',
        )

    def close(self) -> None:
        pass


class _FakeRobots:
    """Robots-гейт, который всё разрешает без сети."""

    def can_fetch(self, url: str) -> bool:
        return True

    def host_unreachable(self, url: str) -> bool:
        return False

    def skip_reason(self, url: str) -> str:
        return ""

    def effective_delay(self, url: str, configured: float) -> float:
        return configured


def _adapter(delay: float, budget: float, calls: list[str], status_code: int = 200) -> CompanySiteAdapter:
    limits = Limits(
        max_pages_per_query=5,
        request_delay_seconds=0.0,
        max_concurrency=1,
        enrich_timeout_seconds=budget,
    )
    return CompanySiteAdapter(
        COMPANY_SITE_CONFIG,
        fetcher=_FakeFetcher(delay, calls, status_code),
        robots=_FakeRobots(),
        limits=limits,
    )


def _company(domain: str = "x.cn") -> LeadCompany:
    return LeadCompany(
        company_name_en="X",
        domain=domain,
        website=f"https://{domain}",
        profile="petcoke_anode",
    )


class TestLimitsTimeout:
    def test_default_enrich_timeout(self):
        assert Limits().enrich_timeout_seconds == 60.0

    def test_enrich_timeout_from_dict(self):
        assert Limits.from_dict({"enrich_timeout_seconds": "30"}).enrich_timeout_seconds == 30.0

    def test_enrich_timeout_clamped_to_minimum(self):
        assert Limits.from_dict({"enrich_timeout_seconds": "0"}).enrich_timeout_seconds == 1.0


class TestEnrichTimeout:
    def test_budget_stops_fetching_contact_pages(self):
        """Бюджет времени не даёт качать контактные страницы после главной."""
        calls: list[str] = []
        adapter = _adapter(delay=0.2, budget=0.05, calls=calls)

        result = adapter.enrich(_company())

        # Главную успели скачать, но контактные пропущены по таймауту.
        assert result.enrich_status == "done"
        assert len(calls) == 1  # только главная страница

    def test_slow_failed_homepage_marks_timeout(self):
        """Медленная и пустая главная → blocked с пометкой timeout."""
        calls: list[str] = []
        adapter = _adapter(delay=0.2, budget=0.05, calls=calls, status_code=500)

        result = adapter.enrich(_company())

        assert result.enrich_status == "blocked"
        assert "timeout" in result.enrich_note.lower()
