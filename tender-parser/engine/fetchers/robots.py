"""robots.txt gate for the leads crawler.

Every URL the leads domain touches goes through :meth:`RobotsGate.can_fetch`
first. Disallowed paths are never requested — they are logged and skipped.

Policy on a robots.txt that cannot be read:

* **4xx** (typically 404) — no robots file exists, everything is allowed.
  This is the behaviour the standard prescribes.
* **5xx, network failure, or a block** — we do not know what is allowed, so we
  allow nothing on that host. Fail closed, not open.

``Crawl-delay`` is honoured when present: the effective delay becomes the
larger of the configured delay and the site's request.
"""

from __future__ import annotations

import threading
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from engine.fetchers.polite_fetcher import PoliteFetcher, SourceBlocked
from engine.observability.logger import get_logger

logger = get_logger("fetcher.robots")


def robots_url_for(url: str) -> str:
    """Return the robots.txt URL for the origin of ``url``."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme or "https", parts.netloc, "/robots.txt", "", ""))


def origin_of(url: str) -> str:
    """Return ``scheme://host[:port]`` for ``url``."""
    parts = urlsplit(url)
    return f"{parts.scheme or 'https'}://{parts.netloc}"


def _ua_token(user_agent: str) -> str:
    """The product token robots.txt rules are matched against.

    ``TenderProLeadsBot/1.0 (+mailto:x@y)`` matches a ``User-agent:
    TenderProLeadsBot`` group.
    """
    return user_agent.split("/")[0].strip() or "*"


class _HostRules:
    """Parsed robots.txt for one origin."""

    __slots__ = ("parser", "allow_all", "deny_all", "crawl_delay", "reason")

    def __init__(
        self,
        parser: RobotFileParser | None = None,
        allow_all: bool = False,
        deny_all: bool = False,
        crawl_delay: float | None = None,
        reason: str = "",
    ):
        self.parser = parser
        self.allow_all = allow_all
        self.deny_all = deny_all
        self.crawl_delay = crawl_delay
        self.reason = reason


class RobotsGate:
    """Per-origin robots.txt cache and permission check.

    One instance is shared across a run so each origin is fetched once.
    """

    def __init__(self, fetcher: PoliteFetcher, user_agent: str | None = None):
        self._fetcher = fetcher
        self._user_agent = user_agent or fetcher.user_agent
        self._token = _ua_token(self._user_agent)
        self._cache: dict[str, _HostRules] = {}
        self._lock = threading.Lock()

    # ── public API ──

    def can_fetch(self, url: str) -> bool:
        """True when robots.txt permits fetching ``url``."""
        rules = self._rules_for(url)
        if rules.deny_all:
            return False
        if rules.allow_all or rules.parser is None:
            return True
        return rules.parser.can_fetch(self._token, url)

    def crawl_delay(self, url: str) -> float | None:
        """Crawl-delay the origin asks for, if any."""
        return self._rules_for(url).crawl_delay

    def effective_delay(self, url: str, configured: float) -> float:
        """The delay to actually use: never shorter than the site asks for."""
        site = self.crawl_delay(url)
        return max(configured, site) if site else configured

    def host_unreachable(self, url: str) -> bool:
        """True, когда robots.txt прочитать не удалось (а не когда он запрещает).

        Различие важно: нечитаемый robots.txt на https — повод попробовать
        http, а явный ``Disallow`` — повод остановиться.
        """
        return self._rules_for(url).deny_all

    def skip_reason(self, url: str) -> str:
        """Human-readable reason a URL is skipped, for logs. '' if allowed."""
        rules = self._rules_for(url)
        if rules.deny_all:
            return rules.reason or "robots.txt unreadable — host skipped"
        if not self.can_fetch(url):
            return "disallowed by robots.txt"
        return ""

    # ── internals ──

    def _rules_for(self, url: str) -> _HostRules:
        origin = origin_of(url)
        with self._lock:
            cached = self._cache.get(origin)
        if cached is not None:
            return cached

        rules = self._load(origin)
        with self._lock:
            self._cache[origin] = rules
        return rules

    def _load(self, origin: str) -> _HostRules:
        """Fetch and parse robots.txt for one origin."""
        url = robots_url_for(origin)
        try:
            response = self._fetcher.fetch(url, raise_on_block=False)
        except SourceBlocked as e:
            logger.warning(f"{origin}: robots.txt blocked ({e.reason}) — skipping host")
            return _HostRules(deny_all=True, reason=f"robots.txt blocked: {e.reason}")
        except Exception as e:
            logger.warning(f"{origin}: robots.txt unreachable ({e}) — skipping host")
            return _HostRules(deny_all=True, reason=f"robots.txt unreachable: {e}")

        if 400 <= response.status_code < 500:
            logger.debug(f"{origin}: no robots.txt (HTTP {response.status_code}) — crawling allowed")
            return _HostRules(allow_all=True)

        if not response.ok:
            logger.warning(
                f"{origin}: robots.txt returned HTTP {response.status_code} — skipping host"
            )
            return _HostRules(
                deny_all=True, reason=f"robots.txt returned HTTP {response.status_code}"
            )

        parser = RobotFileParser()
        parser.set_url(url)
        try:
            parser.parse(response.text.splitlines())
        except Exception as e:
            logger.warning(f"{origin}: robots.txt unparseable ({e}) — skipping host")
            return _HostRules(deny_all=True, reason=f"robots.txt unparseable: {e}")

        delay: float | None = None
        try:
            raw_delay = parser.crawl_delay(self._token)
            if raw_delay is not None:
                delay = float(raw_delay)
        except (AttributeError, TypeError, ValueError):
            delay = None

        logger.debug(f"{origin}: robots.txt loaded (crawl_delay={delay})")
        return _HostRules(parser=parser, crawl_delay=delay)


__all__ = ["RobotsGate", "robots_url_for", "origin_of"]
