"""Tests for monitor/protocols.py: 44-FZ protocol parsing and enrichment."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from monitor.protocols import (
    ProtocolCollector,
    parse_44fz_protocol,
    parse_223fz_protocol,
)
from engine.tests.fixtures import PROTOCOL_44FZ, NOTIFICATION_44FZ_EF


class TestParse44fzProtocol:
    def test_winner_by_rating(self):
        proto = parse_44fz_protocol(PROTOCOL_44FZ)
        assert proto is not None
        assert proto["registry_number"] == "0152300011926000042"
        assert proto["participants_count"] == 3
        assert proto["winner_name"] == 'ООО "ПОДРЯД ПРО"'
        assert proto["winner_inn"] == "5507112233"
        assert proto["winner_price"] == 1062500.0
        assert proto["law_type"] == "44-fz"
        assert proto["protocol_date"] is not None

    def test_winner_by_min_price_without_rating(self):
        xml = PROTOCOL_44FZ.replace("<appRating>1</appRating>", "<x/>") \
                           .replace("<appRating>2</appRating>", "<x/>") \
                           .replace("<appRating>3</appRating>", "<x/>")
        proto = parse_44fz_protocol(xml)
        assert proto["winner_price"] == 1062500.0
        assert proto["winner_name"] == 'ООО "ПОДРЯД ПРО"'

    def test_notification_is_not_protocol(self):
        assert parse_44fz_protocol(NOTIFICATION_44FZ_EF) is None

    def test_invalid_xml(self):
        assert parse_44fz_protocol("мусор") is None


class TestParse223fzProtocol:
    def test_minimal(self):
        xml = """<purchaseProtocol xmlns="http://zakupki.gov.ru/223fz/purchase/1">
          <body><item><purchaseProtocolData>
            <registrationNumber>32615544332</registrationNumber>
            <publicationDateTime>2026-07-22T12:00:00+03:00</publicationDateTime>
            <winnerInfo>
              <name>ООО "ТОПСНАБ"</name>
              <inn>5406778899</inn>
              <price>4320000.00</price>
            </winnerInfo>
          </purchaseProtocolData></item></body>
        </purchaseProtocol>"""
        proto = parse_223fz_protocol(xml)
        assert proto is not None
        assert proto["registry_number"] == "32615544332"
        assert proto["winner_name"] == 'ООО "ТОПСНАБ"'
        assert proto["winner_price"] == 4320000.0
        assert proto["law_type"] == "223-fz"


class _FakeRepo:
    def __init__(self, tenders):
        self._tenders = tenders

    def fetch_existing_by_registry(self, regs):
        return {r: self._tenders[r] for r in regs if r in self._tenders}


class TestEnrichment:
    def test_reduction_pct(self):
        repo = _FakeRepo({"0152300011926000042": {"nmck": 1250000.0}})
        collector = ProtocolCollector.__new__(ProtocolCollector)
        collector._repo = repo

        proto = parse_44fz_protocol(PROTOCOL_44FZ)
        collector._enrich_with_nmck(proto)
        assert proto["nmck"] == 1250000.0
        assert proto["reduction_pct"] == 15.0  # (1250000-1062500)/1250000 = 15%

    def test_unknown_tender_no_reduction(self):
        repo = _FakeRepo({})
        collector = ProtocolCollector.__new__(ProtocolCollector)
        collector._repo = repo
        proto = parse_44fz_protocol(PROTOCOL_44FZ)
        collector._enrich_with_nmck(proto)
        assert "reduction_pct" not in proto
