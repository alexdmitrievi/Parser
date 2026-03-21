"""Базовый класс скрапера с retry, rate limiting и логированием."""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from shared.models import TenderCreate

logger = logging.getLogger(__name__)

# Пул User-Agent для ротации
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]


class BaseScraper(ABC):
    """Абстрактный скрапер. Все конкретные скраперы наследуют от него."""

    platform: str = "unknown"
    base_url: str = ""
    min_delay: float = 2.0
    max_delay: float = 6.0
    timeout: float = 30.0

    def __init__(self) -> None:
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                timeout=self.timeout,
                headers=self._build_headers(),
                follow_redirects=True,
            )
        return self._client

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    def _delay(self) -> None:
        """Задержка между запросами (имитация человека)."""
        sleep_time = random.uniform(self.min_delay, self.max_delay)
        time.sleep(sleep_time)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry {retry_state.attempt_number} for {retry_state.fn.__name__}"
        ),
    )
    def fetch(self, url: str, **kwargs) -> httpx.Response:
        """HTTP GET с retry и rate limiting."""
        self._delay()
        logger.debug(f"[{self.platform}] GET {url}")
        response = self.client.get(url, **kwargs)
        response.raise_for_status()
        return response

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    )
    def post(self, url: str, **kwargs) -> httpx.Response:
        """HTTP POST с retry и rate limiting."""
        self._delay()
        logger.debug(f"[{self.platform}] POST {url}")
        response = self.client.post(url, **kwargs)
        response.raise_for_status()
        return response

    @abstractmethod
    def parse_tenders(self, raw_data) -> list[TenderCreate]:
        """Распарсить сырые данные в список тендеров."""
        ...

    @abstractmethod
    def run(self, **kwargs) -> list[TenderCreate]:
        """Запустить полный цикл парсинга. Возвращает список тендеров."""
        ...

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
