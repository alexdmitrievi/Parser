"""Fetchers: HTTP, Browser (Playwright), FTP."""

from engine.fetchers.http_fetcher import HttpFetcher
from engine.fetchers.browser_fetcher import BrowserFetcher
from engine.fetchers.ftp_fetcher import FtpFetcher

__all__ = ["HttpFetcher", "BrowserFetcher", "FtpFetcher"]
