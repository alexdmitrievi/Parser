"""Browser-based fetcher using Playwright for JS-heavy sites.

Used ONLY when HTTP fetcher can't get the data (JS-rendered content).
Blocks unnecessary resources to minimize overhead.
"""

from __future__ import annotations

import time
from typing import Any

from engine.types import FetchResult, FetchMethod, SourceConfig
from engine.resilience.rate_limiter import RateLimiter
from engine.observability.logger import get_logger

logger = get_logger("fetcher.browser")


class BrowserFetcher:
    """Playwright-based fetcher. Heavyweight — use only when HTTP is insufficient."""

    def __init__(self, config: SourceConfig | None = None, headless: bool = True):
        self._config = config
        self._headless = headless
        self._browser = None
        self._context = None
        self._page = None
        self._rate_limiter = RateLimiter(
            min_delay=config.rate_limit.min_delay if config else 3.0,
            max_delay=config.rate_limit.max_delay if config else 8.0,
        )
        self._source_id = config.source_id if config else "browser"

    def _ensure_browser(self) -> None:
        if self._browser is not None:
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self._headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
            ],
        )

        viewport = {"width": 1280, "height": 800}
        if self._config and self._config.viewport:
            viewport = self._config.viewport

        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport=viewport,
            locale="ru-RU",
        )

        # Block resources that don't affect data
        block_types = ["image", "font", "media"]
        if self._config and self._config.block_resources:
            block_types = self._config.block_resources

        if block_types:
            self._context.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in block_types
                    else route.continue_()
                ),
            )

        self._page = self._context.new_page()

    def fetch(
        self,
        url: str,
        wait_selector: str = "",
        wait_timeout: int = 15000,
        **kwargs: Any,
    ) -> FetchResult:
        """Navigate to URL, wait for selector, return page HTML."""
        self._rate_limiter.wait()
        self._ensure_browser()

        start = time.monotonic()

        selector = wait_selector
        if not selector and self._config:
            selector = self._config.wait_selector

        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=wait_timeout)

            if selector:
                self._page.wait_for_selector(selector, timeout=wait_timeout)

            # Let JS settle
            self._page.wait_for_timeout(1500)

            html = self._page.content()
            elapsed = (time.monotonic() - start) * 1000

            return FetchResult(
                url=url,
                content=html,
                content_type="html",
                status_code=200,
                fetch_method=FetchMethod.BROWSER,
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning(f"[{self._source_id}] Browser fetch failed {url}: {e}")
            raise

    def execute_js(self, script: str) -> Any:
        """Execute JavaScript on the current page."""
        self._ensure_browser()
        return self._page.evaluate(script)

    def scroll_to_bottom(self, pause_ms: int = 1000) -> None:
        """Scroll to bottom for infinite scroll pages."""
        self._ensure_browser()
        self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self._page.wait_for_timeout(pause_ms)

    def fill_and_submit(
        self,
        input_selector: str,
        value: str,
        submit_selector: str = "",
        wait_after_ms: int = 2000,
    ) -> None:
        """Fill a search input and optionally click submit."""
        self._ensure_browser()
        self._page.fill(input_selector, value)
        if submit_selector:
            self._page.click(submit_selector)
        self._page.wait_for_timeout(wait_after_ms)

    def get_current_html(self) -> str:
        """Return current page HTML without navigation."""
        self._ensure_browser()
        return self._page.content()

    def close(self) -> None:
        if self._page:
            self._page.close()
            self._page = None
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if hasattr(self, "_pw") and self._pw:
            self._pw.stop()
            self._pw = None

    def __enter__(self) -> BrowserFetcher:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
