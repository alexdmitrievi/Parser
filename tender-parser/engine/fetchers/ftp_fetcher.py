"""FTP fetcher for EIS XML feeds."""

from __future__ import annotations

import io
import zipfile
from ftplib import FTP
from typing import Any

from engine.types import FetchResult, FetchMethod, SourceConfig
from engine.observability.logger import get_logger

logger = get_logger("fetcher.ftp")


class FtpFetcher:
    """FTP fetcher for downloading XML feeds (primarily EIS/zakupki.gov.ru)."""

    def __init__(self, config: SourceConfig | None = None):
        self._config = config
        self._ftp: FTP | None = None
        self._source_id = config.source_id if config else "ftp"

    def connect(self, host: str, user: str = "anonymous", passwd: str = "") -> None:
        """Establish FTP connection."""
        self._ftp = FTP(timeout=60)
        self._ftp.connect(host)
        self._ftp.login(user, passwd)
        self._ftp.encoding = "utf-8"
        logger.info(f"[{self._source_id}] FTP connected to {host}")

    def list_files(self, directory: str, pattern: str = "*.xml.zip") -> list[str]:
        """List files in FTP directory matching pattern."""
        if not self._ftp:
            raise RuntimeError("FTP not connected")

        try:
            self._ftp.cwd(directory)
            files = self._ftp.nlst()
            suffix = pattern.replace("*", "")
            return [f for f in files if f.endswith(suffix)]
        except Exception as e:
            logger.warning(f"[{self._source_id}] Error listing {directory}: {e}")
            return []

    def download_bytes(self, filepath: str) -> bytes:
        """Download a file as bytes."""
        if not self._ftp:
            raise RuntimeError("FTP not connected")

        buf = io.BytesIO()
        self._ftp.retrbinary(f"RETR {filepath}", buf.write)
        return buf.getvalue()

    def download_and_extract_zip(self, filepath: str) -> list[FetchResult]:
        """Download ZIP, extract XML files, return as FetchResults."""
        raw = self.download_bytes(filepath)
        results: list[FetchResult] = []

        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for name in zf.namelist():
                    if name.endswith(".xml"):
                        xml_bytes = zf.read(name)
                        try:
                            content = xml_bytes.decode("utf-8")
                        except UnicodeDecodeError:
                            content = xml_bytes.decode("cp1251", errors="replace")

                        results.append(FetchResult(
                            url=f"ftp://{filepath}/{name}",
                            content=content,
                            content_type="xml",
                            fetch_method=FetchMethod.FTP,
                        ))
        except zipfile.BadZipFile:
            logger.warning(f"[{self._source_id}] Bad ZIP: {filepath}")

        return results

    def close(self) -> None:
        if self._ftp:
            try:
                self._ftp.quit()
            except Exception:
                try:
                    self._ftp.close()
                except Exception:
                    pass
            self._ftp = None

    def __enter__(self) -> FtpFetcher:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
