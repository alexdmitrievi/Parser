"""Тесты предохранителя недоступной площадки в BaseScraper.

Регрессия: 20.08 прогоны Parse Tenders обрывались по timeout-minutes: 25.
Каждый запрос к zakupki.gov.ru отваливался по ConnectTimeout, а это 3 попытки
с таймаутом ≈ 2.5 минуты. Скрейпер честно перебирал весь список запросов,
съедал весь бюджет времени, и группы ETP / commercial / corporate не
запускались вовсе.
"""

from __future__ import annotations

import httpx
import pytest
from tenacity import RetryError

from scrapers.base import BaseScraper, HostUnreachable


class DeadSiteScraper(BaseScraper):
    """Скрейпер площадки, которая не отвечает никогда."""

    platform = "dead-site"
    base_url = "https://dead.example"
    min_delay = 0.0
    max_delay = 0.0

    def __init__(self, fail_always: bool = True):
        super().__init__()
        self.fail_always = fail_always
        self.attempts = 0

    def _fetch_once(self, url: str, **kwargs):  # обходим tenacity в тесте
        self.attempts += 1
        if self.fail_always:
            raise RetryError(last_attempt=None)
        return httpx.Response(200, text="ok", request=httpx.Request("GET", url))

    def parse_tenders(self, *a, **k):
        return []

    def run(self, *a, **k):
        return []


class TestCircuitBreaker:
    def test_healthy_scraper_is_not_tripped(self):
        s = DeadSiteScraper(fail_always=False)
        for _ in range(10):
            s.fetch("https://dead.example/x")
        assert s.unreachable is False
        assert s.attempts == 10

    def test_trips_after_configured_failures(self):
        s = DeadSiteScraper()
        for _ in range(s.max_consecutive_failures):
            with pytest.raises(RetryError):
                s.fetch("https://dead.example/x")
        assert s.unreachable is True

    def test_further_requests_are_not_attempted(self):
        """Главное: после срабатывания запросы не уходят в сеть вообще."""
        s = DeadSiteScraper()
        for _ in range(s.max_consecutive_failures):
            with pytest.raises(RetryError):
                s.fetch("https://dead.example/x")

        attempts_before = s.attempts
        for _ in range(50):
            with pytest.raises(HostUnreachable):
                s.fetch("https://dead.example/y")
        assert s.attempts == attempts_before, "после срабатывания сеть не трогаем"

    def test_success_resets_the_counter(self):
        s = DeadSiteScraper()
        with pytest.raises(RetryError):
            s.fetch("https://dead.example/x")
        assert s._consecutive_failures == 1

        s.fail_always = False
        s.fetch("https://dead.example/x")
        assert s._consecutive_failures == 0
        assert s.unreachable is False

    def test_each_scraper_instance_gets_a_fresh_chance(self):
        """Новый прогон другой группы источников не наследует срыв."""
        first = DeadSiteScraper()
        for _ in range(first.max_consecutive_failures):
            with pytest.raises(RetryError):
                first.fetch("https://dead.example/x")
        assert first.unreachable is True

        second = DeadSiteScraper(fail_always=False)
        assert second.unreachable is False
        second.fetch("https://dead.example/x")

    def test_threshold_is_configurable(self):
        class Impatient(DeadSiteScraper):
            max_consecutive_failures = 1

        s = Impatient()
        with pytest.raises(RetryError):
            s.fetch("https://dead.example/x")
        assert s.unreachable is True
