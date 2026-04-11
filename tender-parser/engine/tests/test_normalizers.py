"""Tests for engine.normalizers — law_type, purchase_method, tender_normalizer."""

import pytest
from datetime import datetime

from engine.normalizers.law_type import detect_law_type
from engine.normalizers.purchase_method import normalize_purchase_method
from engine.normalizers.tender_normalizer import TenderNormalizer
from engine.types import ParsedRecord


class TestDetectLawType:
    def test_44fz_by_registry_number(self):
        assert detect_law_type("0373100038724000015", "") == "44-fz"

    def test_223fz_by_registry_number(self):
        assert detect_law_type("31907577905", "") == "223-fz"

    def test_44fz_by_source(self):
        assert detect_law_type(None, "roseltorg") == "44-fz"

    def test_223fz_by_source(self):
        assert detect_law_type(None, "gazprom") == "223-fz"

    def test_unknown_defaults_to_commercial(self):
        assert detect_law_type(None, "unknown_source") == "commercial"


class TestNormalizePurchaseMethod:
    def test_auction(self):
        assert normalize_purchase_method("Электронный аукцион") == "auction"

    def test_zapros_kotirovok(self):
        assert normalize_purchase_method("Запрос ценовых котировок") == "quotation"

    def test_konkurs(self):
        assert normalize_purchase_method("Открытый конкурс в электронной форме") == "contest"

    def test_none(self):
        assert normalize_purchase_method(None) is None

    def test_empty(self):
        assert normalize_purchase_method("") is None


class TestTenderNormalizer:
    def test_basic_normalize(self):
        record = ParsedRecord(
            source_id="gazprom",
            registry_number="123456",
            title="Test Tender",
            original_url="https://example.com/tender/123456",
            nmck=1000000.0,
            raw_data={},
        )
        normalizer = TenderNormalizer()
        result = normalizer.normalize(record)

        assert result["source_platform"] == "gazprom"
        assert result["registry_number"] == "123456"
        assert result["title"] == "Test Tender"
        assert result["nmck"] == 1000000.0
        assert result["law_type"] == "223-fz"  # Gazprom → 223-fz

    def test_batch_normalize(self):
        records = [
            ParsedRecord(
                source_id="eis_api",
                registry_number="0373100038724000015",
                title="Тест",
                original_url="https://zakupki.gov.ru/test",
                raw_data={},
            ),
        ]
        normalizer = TenderNormalizer()
        results = normalizer.normalize_batch(records)

        assert len(results) == 1
        assert results[0]["law_type"] == "44-fz"
