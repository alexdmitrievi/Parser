"""Tests for monitor/: карточка уведомления, дедуп уведомлений, PG row prep."""

import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from monitor.notifier import format_card, notify_new_tenders
from monitor.business_filter import BusinessFilter


TENDER = {
    "registry_number": "0152300011926000042",
    "title": "Выполнение работ по расчистке территории от аварийных деревьев",
    "customer_region": "Омская область",
    "law_type": "44-fz",
    "nmck": 1250000.0,
    "purchase_method": "Электронный аукцион",
    "submission_deadline": datetime(2026, 7, 22, 8, 0),
    "application_guarantee": 12500.0,
    "contract_guarantee": 62500.0,
    "original_url": "https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0152300011926000042",
    "okpd2_codes": ["43.12.11.100"],
}


class TestCard:
    def test_card_contains_required_fields(self):
        card = format_card(TENDER)
        assert "1 250 000 ₽" in card          # НМЦК
        assert "44-ФЗ" in card
        assert "Омская область" in card       # регион
        assert "Электронный аукцион" in card  # способ закупки
        assert "22.07.2026 08:00" in card     # дедлайн подачи
        assert "12 500 ₽" in card             # обеспечение заявки
        assert "62 500 ₽" in card             # обеспечение контракта
        assert "regNumber=0152300011926000042" in card  # ссылка

    def test_card_no_action_buttons_plain_text(self):
        card = format_card(TENDER)
        assert "callback_data" not in card
        assert "reply_markup" not in card

    def test_card_handles_missing_fields(self):
        card = format_card({"title": "Тест"})
        assert "—" in card
        assert "Тест" in card

    def test_card_escapes_html(self):
        card = format_card({**TENDER, "title": "Снос <старого> корпуса & пристройки"})
        assert "&lt;старого&gt;" in card
        assert "&amp;" in card


class _FakeRepo:
    def __init__(self, tenders):
        self.tenders = tenders
        self.notified: list[str] = []

    def fetch_unnotified_tenders(self, since_hours=48):
        return [t for t in self.tenders if t["registry_number"] not in self.notified]

    def mark_notified(self, regs):
        self.notified.extend(regs)


class TestNotifyDedup:
    def test_no_duplicate_notifications(self, monkeypatch):
        sent = []
        monkeypatch.setattr("monitor.notifier.send_message", lambda text: sent.append(text) or True)

        bf = BusinessFilter({
            "regions": ["Омская область"], "laws": ["44-ФЗ"],
            "nmck": {"min": 300000, "max": 10000000},
            "keywords": ["расчистка территории"], "okpd2_prefixes": [], "stop_words": [],
        })
        repo = _FakeRepo([dict(TENDER)])

        stats1 = notify_new_tenders(repo, bf)
        assert stats1["sent"] == 1
        # Повторный цикл: тендер уже помечен — карточка не дублируется
        stats2 = notify_new_tenders(repo, bf)
        assert stats2["sent"] == 0
        assert len(sent) == 1

    def test_failed_send_not_marked(self, monkeypatch):
        monkeypatch.setattr("monitor.notifier.send_message", lambda text: False)
        bf = BusinessFilter({"keywords": ["расчистка"], "nmck": {}})
        repo = _FakeRepo([dict(TENDER)])
        stats = notify_new_tenders(repo, bf)
        assert stats["matched"] == 1
        assert stats["sent"] == 0
        assert repo.notified == []  # придёт повторная попытка в следующем цикле


class TestPostgresRowPrep:
    def test_prepare_row_shapes_columns(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
        from engine.persistence.postgres_repo import PostgresTenderRepository, _TENDER_COLUMNS

        repo = PostgresTenderRepository()
        row = repo._prepare_row({
            "source_platform": "eis",
            "registry_number": "123",
            "title": "Тест",
            "nmck": 100.0,
            "publish_date": datetime(2026, 7, 14, 9, 0),
            "raw_data": {"a": 1},
            "documents_urls": [{"u": "x"}],  # выбрасывается
            "okpd2_codes": None,
        })
        assert set(row.keys()) == set(_TENDER_COLUMNS)
        assert row["publish_date"] == "2026-07-14T09:00:00"
        assert row["raw_data"] == '{"a": 1}'
        assert row["okpd2_codes"] == []
        assert row["currency"] == "RUB"
        assert row["status"] == "active"
