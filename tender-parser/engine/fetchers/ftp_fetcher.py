"""FTP fetcher for EIS XML feeds."""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from ftplib import FTP
from typing import Any, Iterator

from engine.types import FetchResult, FetchMethod, SourceConfig
from engine.observability.logger import get_logger

logger = get_logger("fetcher.ftp")


def _decode_xml_bytes(xml_bytes: bytes) -> str:
    try:
        return xml_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return xml_bytes.decode("cp1251", errors="replace")


def iter_local_zip_xml(
    local_path: str,
    skip_name_parts: tuple[str, ...] = (),
    delete_after: bool = True,
) -> Iterator[tuple[str, str]]:
    """Yield (inner_name, xml_content) for each XML in a local ZIP archive.

    Единая точка распаковки выгрузок ЕИС (извещения и протоколы). Битый ZIP
    логируется и пропускается; при delete_after архив удаляется с диска
    после обработки — XML тяжёлые, диск копить их не должен.
    """
    try:
        with zipfile.ZipFile(local_path) as zf:
            for name in zf.namelist():
                if not name.endswith(".xml"):
                    continue
                if any(part in name for part in skip_name_parts):
                    continue
                yield name, _decode_xml_bytes(zf.read(name))
    except zipfile.BadZipFile:
        logger.warning(f"Bad ZIP: {local_path}")
    finally:
        if delete_after:
            try:
                os.unlink(local_path)
            except OSError:
                pass


class FtpFetcher:
    """FTP fetcher for downloading XML feeds (primarily EIS/zakupki.gov.ru)."""

    def __init__(self, config: SourceConfig | None = None):
        self._config = config
        self._ftp: FTP | None = None
        self._source_id = config.source_id if config else "ftp"

    def connect(self, host: str, user: str = "anonymous", passwd: str = "", timeout: int = 60) -> None:
        """Establish FTP connection."""
        self._ftp = FTP(timeout=timeout)
        self._ftp.connect(host)
        self._ftp.login(user, passwd)
        self._ftp.encoding = "utf-8"
        logger.info(f"[{self._source_id}] FTP connected to {host}")

    @property
    def connected(self) -> bool:
        return self._ftp is not None

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

    def list_dirs(self, directory: str) -> list[str]:
        """List entry names in an FTP directory (files and subdirectories)."""
        if not self._ftp:
            raise RuntimeError("FTP not connected")
        try:
            self._ftp.cwd(directory)
            return self._ftp.nlst()
        except Exception as e:
            logger.warning(f"[{self._source_id}] Error listing dirs {directory}: {e}")
            return []

    def download_bytes(self, filepath: str) -> bytes:
        """Download a file as bytes."""
        if not self._ftp:
            raise RuntimeError("FTP not connected")

        buf = io.BytesIO()
        self._ftp.retrbinary(f"RETR {filepath}", buf.write)
        return buf.getvalue()

    def download_to_file(self, filepath: str, dest_dir: str | None = None) -> str:
        """Download a file to local disk, return the local path.

        Caller is responsible for deleting the file (see iter_zip_xml which
        deletes it automatically after extraction).
        """
        if not self._ftp:
            raise RuntimeError("FTP not connected")

        fd, local_path = tempfile.mkstemp(
            suffix=os.path.basename(filepath), dir=dest_dir
        )
        try:
            with os.fdopen(fd, "wb") as f:
                self._ftp.retrbinary(f"RETR {filepath}", f.write)
        except Exception:
            try:
                os.unlink(local_path)
            except OSError:
                pass
            raise
        return local_path

    def iter_zip_xml(self, filepath: str, dest_dir: str | None = None) -> Iterator[tuple[str, str]]:
        """Download ZIP to disk, yield (inner_name, xml_content) per XML entry.

        The local archive is deleted from disk once iteration finishes —
        EIS XML dumps are heavy and must not accumulate on the VPS.
        """
        local_path = self.download_to_file(filepath, dest_dir=dest_dir)
        try:
            with zipfile.ZipFile(local_path) as zf:
                for name in zf.namelist():
                    if name.endswith(".xml"):
                        yield name, _decode_xml_bytes(zf.read(name))
        except zipfile.BadZipFile:
            logger.warning(f"[{self._source_id}] Bad ZIP: {filepath}")
        finally:
            try:
                os.unlink(local_path)
            except OSError:
                pass

    def download_and_extract_zip(self, filepath: str) -> list[FetchResult]:
        """Download ZIP, extract XML files, return as FetchResults."""
        raw = self.download_bytes(filepath)
        results: list[FetchResult] = []

        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for name in zf.namelist():
                    if name.endswith(".xml"):
                        results.append(FetchResult(
                            url=f"ftp://{filepath}/{name}",
                            content=_decode_xml_bytes(zf.read(name)),
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
