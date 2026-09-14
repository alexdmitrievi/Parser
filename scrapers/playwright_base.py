"""Базовый класс для Playwright-парсеров.

Используется для площадок, которые блокируют httpx или рендерят контент через JS.
Требует: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional

logger = logging.getLogger(__name__)


class PlaywrightScraper:
    """Базовый класс для парсеров на Playwright."""

    platform: str = ""
    base_url: str = ""
    min_delay: float = 2.0
    max_delay: float = 5.0

    def __init__(self):
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ru-RU",
            viewport={"width": 1280, "height": 800},
        )
        self._page = self._context.new_page()
        return self

    def __exit__(self, *args):
        if self._page:
            self._page.close()
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if hasattr(self, "_pw"):
            self._pw.stop()

    def _delay(self):
        """Случайная задержка между запросами."""
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def goto(self, url: str, wait_selector: Optional[str] = None, timeout: int = 15000) -> str:
        """Перейти на страницу и дождаться загрузки. Возвращает HTML."""
        logger.debug(f"[{self.platform}] goto: {url}")
        self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if wait_selector:
            try:
                self._page.wait_for_selector(wait_selector, timeout=timeout)
            except Exception:
                logger.warning(f"[{self.platform}] selector '{wait_selector}' not found, using page as-is")
        # Дополнительная пауза для JS-рендеринга
        self._page.wait_for_timeout(1500)
        return self._page.content()
