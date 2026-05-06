import sys
import os
import pytest

# Ensure the project root is in sys.path for imports
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def sample_tender_dict():
    return {
        "source_platform": "eis",
        "registry_number": "0173100001525000001",
        "law_type": "44-fz",
        "title": "Капитальный ремонт кровли административного здания",
        "description": "Полный комплекс работ по замене кровельного покрытия",
        "customer_name": 'ГКУ "Дирекция по эксплуатации зданий"',
        "customer_region": "Москва",
        "okpd2_codes": ["43.91.19.110"],
        "nmck": 5800000.00,
        "publish_date": "2026-01-15T00:00:00+00:00",
        "submission_deadline": "2026-02-01T23:59:00+00:00",
        "status": "active",
        "original_url": "https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=0173100001525000001",
        "niche_tags": ["construction"],
        "sources": ["eis"],
    }


@pytest.fixture
def sample_subscription_dict():
    return {
        "telegram_user_id": 123456789,
        "name": "test_user",
        "keywords": ["ремонт", "кровля"],
        "regions": ["Москва"],
        "niche_tags": ["construction"],
        "min_nmck": 1000000,
        "max_nmck": 10000000,
        "law_types": ["44-fz"],
        "okpd2_prefixes": ["43.9"],
    }


@pytest.fixture
def sample_search_filters_dict():
    return {
        "query": "ремонт кровли",
        "region": "Москва",
        "niche": "construction",
        "status": "active",
        "law_type": "44-fz",
        "min_nmck": 1000000,
        "max_nmck": 10000000,
        "page": 1,
        "per_page": 10,
        "sort_by": "created_at",
    }
