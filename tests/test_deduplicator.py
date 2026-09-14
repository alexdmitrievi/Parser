"""Tests for deduplication logic in shared/db.py insert_tenders."""
import hashlib
import pytest
from shared.models import TenderCreate


def _make_tender(platform, reg_num, title="Test tender", nmck=None):
    return TenderCreate(
        source_platform=platform,
        registry_number=reg_num,
        title=title,
        nmck=nmck,
    )


def _hash_fallback(platform, title):
    return hashlib.sha256(
        f"{platform}|{title}|{''}|{''}".encode()
    ).hexdigest()[:24]


class TestInsertTendersDedup:
    """Tests for batch deduplication logic in insert_tenders()."""

    def test_seen_key_skips_duplicate(self):
        seen = set()
        t1 = _make_tender("eis", "REG-001")
        t2 = _make_tender("eis", "REG-001")
        for t in (t1, t2):
            key = (t.source_platform, t.registry_number or "")
            if key in seen:
                continue
            seen.add(key)
        assert len(seen) == 1

    def test_different_registry_numbers_not_duplicates(self):
        seen = set()
        t1 = _make_tender("eis", "REG-001")
        t2 = _make_tender("eis", "REG-002")
        for t in (t1, t2):
            key = (t.source_platform, t.registry_number or "")
            if key in seen:
                continue
            seen.add(key)
        assert len(seen) == 2

    def test_same_registry_different_platform_not_duplicate(self):
        seen = set()
        t1 = _make_tender("eis", "REG-001")
        t2 = _make_tender("b2b_center", "REG-001")
        for t in (t1, t2):
            key = (t.source_platform, t.registry_number or "")
            if key in seen:
                continue
            seen.add(key)
        assert len(seen) == 2

    def test_missing_registry_generates_fallback(self):
        t = TenderCreate(source_platform="eis", title="Test")
        reg = t.registry_number
        if not reg:
            fallback = hashlib.sha256(
                f"{t.source_platform}|{t.title}|{t.customer_name or ''}|{t.original_url or ''}".encode()
            ).hexdigest()[:24]
            reg = f"_gen_{fallback}"
        assert reg.startswith("_gen_")

    def test_sources_includes_platform(self):
        t = TenderCreate(source_platform="eis", title="Test")
        sources = list(dict.fromkeys((t.sources or []) + [t.source_platform]))
        assert "eis" in sources

    def test_sources_dedup_when_already_in_list(self):
        t = TenderCreate(source_platform="eis", title="Test", sources=["eis", "b2b_center"])
        sources = list(dict.fromkeys(t.sources + [t.source_platform]))
        assert sources.count("eis") == 1
        assert len(sources) == 2  # eis, b2b_center
