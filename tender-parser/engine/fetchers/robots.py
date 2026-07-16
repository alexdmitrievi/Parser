"""Проверка robots.txt для коммерческих площадок.

Правило проекта: скрейпим только публичные страницы поиска и только то,
что разрешает robots.txt. Обход авторизации и антибот-защиты запрещён.
"""

from __future__ import annotations

import urllib.robotparser
from urllib.parse import urlsplit

import httpx

from engine.observability.logger import get_logger

logger = get_logger("fetcher.robots")

DEFAULT_USER_AGENT = "TenderMonitorBot/1.0 (+personal procurement monitoring)"


class RobotsChecker:
    """Кэширующий чекер robots.txt (один парсер на origin)."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self._user_agent = user_agent
        self._cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _get_parser(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        if origin in self._cache:
            return self._cache[origin]

        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = httpx.get(
                f"{origin}/robots.txt",
                timeout=15,
                follow_redirects=True,
                headers={"User-Agent": self._user_agent},
            )
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                self._cache[origin] = rp
            elif resp.status_code in (401, 403):
                # Сайт закрывает robots.txt — консервативно считаем всё запрещённым
                logger.warning(f"{origin}/robots.txt → {resp.status_code}, treating as disallow-all")
                rp.disallow_all = True
                self._cache[origin] = rp
            else:
                # 404 и прочее: robots.txt нет — ограничений нет
                self._cache[origin] = None
        except Exception as e:
            logger.warning(f"Cannot fetch {origin}/robots.txt: {e} — allowing by default")
            self._cache[origin] = None

        return self._cache[origin]

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        rp = self._get_parser(origin)
        if rp is None:
            return True
        return rp.can_fetch(self._user_agent, url)


_checker: RobotsChecker | None = None


def get_robots_checker() -> RobotsChecker:
    global _checker
    if _checker is None:
        _checker = RobotsChecker()
    return _checker
