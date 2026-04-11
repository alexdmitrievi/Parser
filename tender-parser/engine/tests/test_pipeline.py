"""Tests for engine.pipeline — deduplicator, versioner, tagger."""

import pytest
from engine.pipeline.deduplicator import Deduplicator
from engine.pipeline.versioner import ChangeDetector
from engine.pipeline.tagger import NicheTagger
from engine.types import CrawlAction


class TestDeduplicator:
    def test_insert_new(self):
        dedup = Deduplicator()
        incoming = {"registry_number": "NEW123", "title": "test", "source_platform": "eis"}
        existing_map = {}
        assert dedup.check(incoming, existing_map) == CrawlAction.INSERT

    def test_update_existing_higher_priority(self):
        dedup = Deduplicator()
        incoming = {
            "registry_number": "123",
            "title": "updated",
            "source_platform": "eis",
            "nmck": 1000,
        }
        existing_map = {
            "123": {"registry_number": "123", "title": "old", "source_platform": "rostender"},
        }
        result = dedup.check(incoming, existing_map)
        assert result == CrawlAction.UPDATE

    def test_insert_without_registry(self):
        dedup = Deduplicator()
        incoming = {"title": "no registry", "source_platform": "test"}
        assert dedup.check(incoming, {}) == CrawlAction.INSERT


class TestChangeDetector:
    def test_detect_price_change(self):
        detector = ChangeDetector()
        existing = {"nmck": 1000000.0, "status": "active"}
        incoming = {"nmck": 1500000.0, "status": "active"}
        changes = detector.detect_changes(existing, incoming)
        assert "nmck" in changes
        assert changes["nmck"] == (1000000.0, 1500000.0)

    def test_no_changes(self):
        detector = ChangeDetector()
        record = {"status": "active", "nmck": 1000}
        changes = detector.detect_changes(record, record)
        assert len(changes) == 0

    def test_significant_change(self):
        detector = ChangeDetector()
        changes = {"status": ("active", "completed"), "title": ("A", "B")}
        assert detector.is_significant_change(changes) is True

    def test_insignificant_change(self):
        detector = ChangeDetector()
        changes = {"title": ("A", "B")}
        assert detector.is_significant_change(changes) is False


class TestNicheTagger:
    def test_furniture_keyword(self):
        tagger = NicheTagger()
        record = {"title": "Поставка мебели офисной", "description": ""}
        tags = tagger.tag(record)
        assert "furniture" in tags

    def test_construction_keyword(self):
        tagger = NicheTagger()
        record = {"title": "Капитальный ремонт здания", "description": ""}
        tags = tagger.tag(record)
        assert "construction" in tags

    def test_no_match(self):
        tagger = NicheTagger()
        record = {"title": "Поставка молочных продуктов", "description": ""}
        tags = tagger.tag(record)
        assert tags == []

    def test_okpd2_match(self):
        tagger = NicheTagger()
        record = {"title": "Поставка", "description": "", "okpd2_codes": ["31.09.1"]}
        tags = tagger.tag(record)
        assert "furniture" in tags
