"""Тесты проверки robots.txt, вежливого режима и реакции на блокировку."""

from __future__ import annotations

import pytest

from engine.fetchers.polite_fetcher import (
    PoliteResponse,
    SourceBlocked,
    looks_like_captcha,
    parse_retry_after,
)
from engine.fetchers.robots import RobotsGate, origin_of, robots_url_for


class FakeFetcher:
    """Фетчер-заглушка: отдаёт заранее заданные ответы по URL."""

    def __init__(self, responses: dict[str, PoliteResponse | Exception], user_agent: str = "TestBot/1.0"):
        self.user_agent = user_agent
        self.responses = responses
        self.requested: list[str] = []

    def fetch(self, url: str, *, raise_on_block: bool = True, **kwargs) -> PoliteResponse:
        self.requested.append(url)
        reply = self.responses.get(url)
        if reply is None:
            return PoliteResponse(url=url, status_code=404)
        if isinstance(reply, Exception):
            raise reply
        return reply


def robots_response(url: str, body: str, status: int = 200) -> PoliteResponse:
    return PoliteResponse(url=url, status_code=status, text=body)


ROBOTS_URL = "https://example.cn/robots.txt"


class TestRobotsGate:
    def test_allows_paths_not_disallowed(self):
        gate = RobotsGate(FakeFetcher({
            ROBOTS_URL: robots_response(ROBOTS_URL, "User-agent: *\nDisallow: /private/\n")
        }))
        assert gate.can_fetch("https://example.cn/contact") is True

    def test_blocks_disallowed_paths(self):
        gate = RobotsGate(FakeFetcher({
            ROBOTS_URL: robots_response(ROBOTS_URL, "User-agent: *\nDisallow: /private/\n")
        }))
        assert gate.can_fetch("https://example.cn/private/secret.html") is False

    def test_blocks_everything_when_disallow_all(self):
        gate = RobotsGate(FakeFetcher({
            ROBOTS_URL: robots_response(ROBOTS_URL, "User-agent: *\nDisallow: /\n")
        }))
        assert gate.can_fetch("https://example.cn/anything") is False

    def test_honours_rules_for_our_bot_token(self):
        body = "User-agent: TenderProLeadsBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        gate = RobotsGate(
            FakeFetcher({ROBOTS_URL: robots_response(ROBOTS_URL, body)},
                        user_agent="TenderProLeadsBot/1.0 (+mailto:a@b.c)")
        )
        assert gate.can_fetch("https://example.cn/contact") is False

    def test_missing_robots_allows_crawling(self):
        """404 — файла нет, обход разрешён (так предписывает стандарт)."""
        gate = RobotsGate(FakeFetcher({ROBOTS_URL: PoliteResponse(url=ROBOTS_URL, status_code=404)}))
        assert gate.can_fetch("https://example.cn/contact") is True

    def test_server_error_denies_whole_host(self):
        """5xx — что разрешено, неизвестно. Не идём никуда: fail closed."""
        gate = RobotsGate(FakeFetcher({ROBOTS_URL: PoliteResponse(url=ROBOTS_URL, status_code=503)}))
        assert gate.can_fetch("https://example.cn/contact") is False
        assert gate.host_unreachable("https://example.cn/contact") is True

    def test_network_failure_denies_whole_host(self):
        gate = RobotsGate(FakeFetcher({ROBOTS_URL: ConnectionError("refused")}))
        assert gate.can_fetch("https://example.cn/contact") is False
        assert gate.host_unreachable("https://example.cn/contact") is True

    def test_blocked_robots_denies_whole_host(self):
        gate = RobotsGate(FakeFetcher({ROBOTS_URL: SourceBlocked(ROBOTS_URL, "HTTP 403", 403)}))
        assert gate.can_fetch("https://example.cn/contact") is False

    def test_explicit_disallow_is_not_unreachable(self):
        """Явный запрет и нечитаемый файл различаются."""
        gate = RobotsGate(FakeFetcher({
            ROBOTS_URL: robots_response(ROBOTS_URL, "User-agent: *\nDisallow: /\n")
        }))
        assert gate.can_fetch("https://example.cn/x") is False
        assert gate.host_unreachable("https://example.cn/x") is False

    def test_fetches_robots_once_per_origin(self):
        fetcher = FakeFetcher({
            ROBOTS_URL: robots_response(ROBOTS_URL, "User-agent: *\nAllow: /\n")
        })
        gate = RobotsGate(fetcher)
        for path in ("/a", "/b", "/c"):
            gate.can_fetch(f"https://example.cn{path}")
        assert fetcher.requested.count(ROBOTS_URL) == 1

    def test_honours_crawl_delay(self):
        gate = RobotsGate(FakeFetcher({
            ROBOTS_URL: robots_response(ROBOTS_URL, "User-agent: *\nCrawl-delay: 10\n")
        }))
        assert gate.crawl_delay("https://example.cn/x") == 10.0
        assert gate.effective_delay("https://example.cn/x", configured=3.0) == 10.0

    def test_configured_delay_wins_when_larger(self):
        gate = RobotsGate(FakeFetcher({
            ROBOTS_URL: robots_response(ROBOTS_URL, "User-agent: *\nCrawl-delay: 1\n")
        }))
        assert gate.effective_delay("https://example.cn/x", configured=5.0) == 5.0

    def test_skip_reason_is_reported(self):
        gate = RobotsGate(FakeFetcher({
            ROBOTS_URL: robots_response(ROBOTS_URL, "User-agent: *\nDisallow: /private/\n")
        }))
        assert gate.skip_reason("https://example.cn/private/x") == "disallowed by robots.txt"
        assert gate.skip_reason("https://example.cn/ok") == ""

    def test_http_and_https_are_separate_origins(self):
        fetcher = FakeFetcher({
            "https://example.cn/robots.txt": ConnectionError("no tls"),
            "http://example.cn/robots.txt": robots_response(
                "http://example.cn/robots.txt", "User-agent: *\nAllow: /\n"
            ),
        })
        gate = RobotsGate(fetcher)
        assert gate.can_fetch("https://example.cn/contact") is False
        assert gate.can_fetch("http://example.cn/contact") is True


class TestHelpers:
    def test_robots_url_for(self):
        assert robots_url_for("https://example.cn/a/b?c=1") == "https://example.cn/robots.txt"

    def test_origin_of(self):
        assert origin_of("https://example.cn/a/b") == "https://example.cn"


class TestBlockDetection:
    @pytest.mark.parametrize(
        "body",
        [
            "<html><body>Please complete the captcha</body></html>",
            "<html><title>Just a moment...</title></html>",
            "<html>checking your browser before accessing</html>",
            "<html>请输入验证码</html>",
            "<html>安全验证</html>",
        ],
    )
    def test_recognises_captcha_walls(self, body):
        assert looks_like_captcha(body) is True

    def test_normal_page_is_not_a_captcha(self):
        assert looks_like_captcha("<html><body>Contact us at info@x.cn</body></html>") is False

    def test_empty_body_is_not_a_captcha(self):
        assert looks_like_captcha("") is False


class TestRetryAfter:
    @pytest.mark.parametrize("raw,expected", [("120", 120.0), ("0", 0.0), ("  30 ", 30.0)])
    def test_parses_delay_seconds(self, raw, expected):
        assert parse_retry_after(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "not-a-date"])
    def test_returns_none_for_unusable_values(self, raw):
        assert parse_retry_after(raw) is None

    def test_parses_http_date(self):
        # Дата в прошлом — ждать нечего, но разобраться должно.
        assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0
