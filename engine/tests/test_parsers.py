"""Tests for engine.parsers.utils — price, date, text parsing."""

import pytest
from datetime import datetime
from engine.parsers.utils import parse_price, parse_date, clean_text, parse_registry_number


class TestParsePrice:
    def test_simple_decimal(self):
        assert parse_price("1500000.00") == 1500000.0

    def test_russian_format_with_spaces(self):
        assert parse_price("2 500 000,50 руб.") == 2500000.5

    def test_nbsp(self):
        assert parse_price("1\xa0250\xa0000,00 ₽") == 1250000.0

    def test_plain_integer(self):
        assert parse_price("850000") == 850000.0

    def test_empty(self):
        assert parse_price("") is None
        assert parse_price(None) is None

    def test_garbage(self):
        assert parse_price("не указана") is None

    def test_zero(self):
        assert parse_price("0.00") is None  # We skip zero prices


class TestParseDate:
    def test_dd_mm_yyyy(self):
        assert parse_date("15.04.2025") == datetime(2025, 4, 15)

    def test_dd_mm_yyyy_hh_mm(self):
        assert parse_date("20.04.2025 14:00") == datetime(2025, 4, 20, 14, 0)

    def test_iso_format(self):
        assert parse_date("2025-04-15") == datetime(2025, 4, 15)

    def test_russian_month(self):
        result = parse_date("15 апреля 2025")
        assert result == datetime(2025, 4, 15)

    def test_empty(self):
        assert parse_date("") is None
        assert parse_date(None) is None


class TestCleanText:
    def test_strips_whitespace(self):
        assert clean_text("  hello world  ") == "hello world"

    def test_collapses_spaces(self):
        assert clean_text("hello   world") == "hello world"

    def test_strips_newlines(self):
        assert clean_text("hello\n\nworld") == "hello world"

    def test_none(self):
        assert clean_text(None) == ""

    def test_nbsp(self):
        assert clean_text("hello\xa0world") == "hello world"


class TestParseRegistryNumber:
    def test_extract_from_text(self):
        result = parse_registry_number("№ 0373100038724000015")
        assert result == "0373100038724000015"

    def test_extract_from_url(self):
        result = parse_registry_number("/purchase/0012345")
        assert result == "0012345"

    def test_short_numbers_ignored(self):
        result = parse_registry_number("12")
        assert result is None

    def test_empty(self):
        assert parse_registry_number("") is None
