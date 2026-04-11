"""Tests for engine source adapters — corporate, EIS, B2B Center."""

import pytest
from engine.types import FetchResult, SourceCategory, FetchMethod, RateLimitConfig, SourceConfig
from engine.sources.tenders.corporate import CorporateSourceAdapter, get_all_corporate_adapters
from engine.sources.tenders.eis_api import EisApiSourceAdapter, EIS_API_CONFIG
from engine.sources.tenders.b2b_center import B2BCenterSourceAdapter, B2B_CENTER_CONFIG


class TestCorporateAdapter:
    def test_parse_listing(self, corporate_html_page, sample_source_config):
        adapter = CorporateSourceAdapter(sample_source_config)
        result = FetchResult(
            url="https://example.com/search",
            status_code=200,
            content=corporate_html_page,
            content_type="text/html",
            elapsed_ms=100,
        )

        records = adapter.parse_listing(result)
        assert len(records) == 3

        # First record: full data
        assert records[0].registry_number is not None
        assert records[0].nmck == 2500000.5
        assert records[0].customer_name == "ПАО Газпром"

        # Third record: no price, no deadline
        assert records[2].nmck is None

    def test_all_corporate_sources_created(self):
        adapters = get_all_corporate_adapters()
        assert len(adapters) == 6
        ids = {a.source_id for a in adapters}
        assert ids == {"gazprom", "rosatom", "rosneft", "lukoil", "nornickel", "mts"}

    def test_discover_urls(self, sample_source_config):
        cfg = SourceConfig(
            source_id="test",
            platform_name="test",
            category=SourceCategory.TENDERS,
            base_url="https://example.com",
            fetch_method=FetchMethod.HTTP,
            search_queries=["q1", "q2"],
            max_pages=2,
            endpoints={"search": "/s", "query_param": "q", "page_param": "p"},
            rate_limit=RateLimitConfig(min_delay=0, max_delay=0),
        )
        adapter = CorporateSourceAdapter(cfg)
        urls = adapter.discover()
        # 2 queries × 2 pages = 4 URLs
        assert len(urls) == 4
        assert "q=q1" in urls[0]
        assert "p=2" in urls[1]


class TestEisApiAdapter:
    def test_parse_listing(self, eis_html_page):
        adapter = EisApiSourceAdapter(EIS_API_CONFIG)
        result = FetchResult(
            url="https://zakupki.gov.ru/search",
            status_code=200,
            content=eis_html_page,
            content_type="text/html",
            elapsed_ms=150,
        )

        records = adapter.parse_listing(result)
        assert len(records) == 1
        assert records[0].registry_number == "0373100038724000015"
        assert records[0].law_type == "44-fz"
        assert records[0].nmck == 1250000.0
        assert records[0].customer_name is not None
        assert "Москв" in (records[0].customer_region or "")


class TestB2BCenterAdapter:
    def test_parse_listing(self, b2b_html_page):
        adapter = B2BCenterSourceAdapter(B2B_CENTER_CONFIG)
        result = FetchResult(
            url="https://www.b2b-center.ru/market/",
            status_code=200,
            content=b2b_html_page,
            content_type="text/html",
            elapsed_ms=100,
        )

        records = adapter.parse_listing(result)
        assert len(records) == 2

        # First record
        assert records[0].registry_number == "9876543"
        assert "мебели" in records[0].title.lower()
        assert records[0].customer_name == "ООО ТестКомпани"

        # Second record: prefix stripped
        assert "Ремонт помещений" in records[1].title
