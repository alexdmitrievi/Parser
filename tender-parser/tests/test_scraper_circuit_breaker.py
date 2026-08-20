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


class TestConnectTimeout:
    """Подключение и чтение таймаутятся отдельно.

    Площадки, закрытые для зарубежных адресов, не отвечают на рукопожатие.
    Общий таймаут 30 с тратился на них целиком; отдельный connect-таймаут
    выясняет это за секунды, не мешая медленным, но живым ответам.
    """

    def test_connect_timeout_is_shorter_than_read(self):
        s = DeadSiteScraper()
        timeout = s.client.timeout
        assert timeout.connect == s.connect_timeout
        assert timeout.read == s.timeout
        assert timeout.connect < timeout.read

    def test_connect_timeout_never_exceeds_total(self):
        class Odd(DeadSiteScraper):
            timeout = 5.0
            connect_timeout = 60.0

        assert Odd().client.timeout.connect == 5.0

    def test_budget_fits_the_workflow_limit(self):
        """Девять мёртвых площадок должны укладываться в timeout-minutes: 25."""
        s = DeadSiteScraper()
        attempts_per_failure = 3
        worst_attempt = s.connect_timeout + s.max_delay
        per_scraper = worst_attempt * attempts_per_failure * s.max_consecutive_failures
        assert per_scraper * 9 < 25 * 60, "группа all не укладывается в лимит"
