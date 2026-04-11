"""Shared test fixtures for engine tests."""

from __future__ import annotations

import pytest
from datetime import datetime

from engine.types import (
    SourceConfig, SourceCategory, FetchMethod, FetchResult,
    ParsedRecord, RateLimitConfig,
)


@pytest.fixture
def sample_source_config() -> SourceConfig:
    """Minimal SourceConfig for testing."""
    return SourceConfig(
        source_id="test_source",
        platform_name="test",
        category=SourceCategory.TENDERS,
        base_url="https://example.com",
        fetch_method=FetchMethod.HTTP,
        search_queries=["тест"],
        max_pages=1,
        rate_limit=RateLimitConfig(min_delay=0.0, max_delay=0.0),
    )


@pytest.fixture
def sample_fetch_result() -> FetchResult:
    """Minimal FetchResult for testing."""
    return FetchResult(
        url="https://example.com/search?q=test",
        status_code=200,
        content="<html><body>test</body></html>",
        content_type="text/html",
        elapsed_ms=100,
    )


@pytest.fixture
def sample_parsed_record() -> ParsedRecord:
    """Minimal ParsedRecord for testing."""
    return ParsedRecord(
        source_id="test_source",
        registry_number="12345678",
        title="Тестовая закупка мебели",
        original_url="https://example.com/tender/12345678",
        nmck=1500000.0,
        customer_name="ООО Тест",
        customer_region="Омская область",
        submission_deadline=datetime(2025, 3, 1, 12, 0),
        raw_data={"test": True},
    )


@pytest.fixture
def corporate_html_page() -> str:
    """Fake HTML page mimicking corporate portal layout."""
    return """
    <html><body>
    <div class="purchase-row">
        <a href="/purchase/001234">Поставка оборудования для газопровода 001234</a>
        <span class="price">2 500 000,50 руб.</span>
        <span class="customer">ПАО Газпром</span>
        <span class="deadline">15.04.2025</span>
    </div>
    <div class="purchase-row">
        <a href="/purchase/001235">Ремонт трубопроводных систем 001235</a>
        <span class="price">850 000 руб.</span>
        <span class="customer">АО Газпром трансгаз</span>
        <span class="deadline">20.04.2025 14:00</span>
    </div>
    <div class="purchase-row">
        <a href="/purchase/001236">Техническое обслуживание АГНКС</a>
        <span class="customer">ООО Газпром ПХГ</span>
    </div>
    </body></html>
    """


@pytest.fixture
def eis_html_page() -> str:
    """Fake HTML page mimicking zakupki.gov.ru search results."""
    return """
    <html><body>
    <div class="search-registry-entry-block">
        <div class="registry-entry__header-top__title">44-ФЗ</div>
        <div class="registry-entry__header-mid__number">
            <a href="/epz/order/notice/ea44/view/common-info.html?regNumber=0373100038724000015">
                № 0373100038724000015
            </a>
        </div>
        <div class="registry-entry__body-value">Поставка канцелярских товаров</div>
        <div class="registry-entry__body-href">
            <a href="#">ГБУ города Москвы «Жилищник»</a>
        </div>
        <div class="price-block__value">1 250 000,00 ₽</div>
        <div class="data-block__value">25.02.2025</div>
        <div class="data-block__value">10.03.2025</div>
    </div>
    </body></html>
    """


@pytest.fixture
def b2b_html_page() -> str:
    """Fake HTML page mimicking b2b-center.ru search results."""
    return """
    <html><body>
    <table class="search-results">
        <tr>
            <td><a href="/market/tender-9876543/">Поставка мебели офисной</a></td>
            <td><a href="/company/123/">ООО ТестКомпани</a></td>
            <td>01.03.2025</td>
            <td>15.03.2025</td>
            <td></td>
        </tr>
        <tr>
            <td><a href="/market/tender-9876544/">Запрос предложений № 9876544 Ремонт помещений</a></td>
            <td>АО Заказчик</td>
            <td>02.03.2025</td>
            <td>20.03.2025</td>
            <td></td>
        </tr>
    </table>
    </body></html>
    """
