"""Integration tests for DB operations (require Supabase connection).

These tests are skipped by default if SUPABASE_URL is not set.
Run with: SUPABASE_URL=xxx SUPABASE_SERVICE_ROLE_KEY=xxx pytest tests/test_db.py -v
"""
import os
import sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"),
    reason="SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required for DB tests",
)


class TestDBConnection:
    def test_get_db_returns_client(self):
        from shared.db import get_db
        client = get_db()
        assert client is not None

    def test_count_tenders(self):
        from shared.db import count_tenders
        from shared.models import SearchFilters
        f = SearchFilters(page=1, per_page=5)
        count = count_tenders(f)
        assert count >= 0

    def test_search_tenders(self):
        from shared.db import search_tenders
        from shared.models import SearchFilters
        f = SearchFilters(page=1, per_page=5)
        rows = search_tenders(f)
        assert isinstance(rows, list)
        if rows:
            assert "id" in rows[0]
            assert "title" in rows[0]

    def test_suggest_regions(self):
        from shared.db import suggest_regions
        items = suggest_regions("Москва", limit=5)
        assert isinstance(items, list)

    def test_suggest_customers(self):
        from shared.db import suggest_customers
        items = suggest_customers("ГКУ", limit=5)
        assert isinstance(items, list)


class TestDBStatsRPC:
    def test_get_stats_via_rpc(self):
        from shared.db import get_stats_via_rpc
        stats = get_stats_via_rpc()
        assert isinstance(stats, dict)
        assert "total" in stats
        assert stats["total"] >= 0

    def test_get_meta_via_rpc(self):
        from shared.db import get_meta_via_rpc
        meta = get_meta_via_rpc()
        assert isinstance(meta, dict)
        assert "niches" in meta
        assert "platforms" in meta
        assert "methods" in meta


class TestDBFunding:
    def test_get_funding_programs(self):
        from shared.db import get_funding_programs
        rows, total = get_funding_programs(page=1, page_size=5)
        assert isinstance(rows, list)
        assert total >= 0

    def test_get_funding_meta(self):
        from shared.db import get_funding_meta_via_rpc
        meta = get_funding_meta_via_rpc()
        assert isinstance(meta, dict)
        assert "total_active" in meta
