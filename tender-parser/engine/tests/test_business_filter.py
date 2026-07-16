"""Tests for monitor/business_filter.py: filter logic + hot reload."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from monitor.business_filter import BusinessFilter, DEFAULT_CONFIG_PATH

CONFIG = {
    "regions": ["Омская область", "Новосибирская область"],
    "laws": ["44-ФЗ", "223-ФЗ"],
    "nmck": {"min": 300000, "max": 10000000},
    "okpd2_prefixes": ["43.11", "43.12", "19.20.28"],
    "keywords": ["снос", "демонтаж", "печное топливо", "текущий ремонт"],
    "stop_words": ["проектирование", "ПИР", "капитальный ремонт многоквартирных"],
}


def make_tender(**overrides):
    tender = {
        "title": "Снос аварийного здания",
        "customer_region": "Омская область",
        "law_type": "44-fz",
        "nmck": 1500000.0,
        "okpd2_codes": [],
    }
    tender.update(overrides)
    return tender


@pytest.fixture
def bf():
    return BusinessFilter(CONFIG)


class TestBaseConditions:
    def test_passes_by_keyword(self, bf):
        assert bf.matches(make_tender()) is True

    def test_passes_by_okpd2_prefix(self, bf):
        t = make_tender(title="Выполнение работ", okpd2_codes=["43.12.11.100"])
        assert bf.matches(t) is True

    def test_fails_without_okpd2_and_keyword(self, bf):
        t = make_tender(title="Поставка канцтоваров", okpd2_codes=["17.23.13"])
        assert bf.matches(t) is False

    def test_okpd2_or_keyword_semantics(self, bf):
        # ОКПД2 мимо, но ключевое слово в наименовании есть → проходит
        t = make_tender(title="Демонтаж перегородок", okpd2_codes=["99.99"])
        assert bf.matches(t) is True


class TestRegion:
    def test_wrong_region(self, bf):
        assert bf.matches(make_tender(customer_region="Томская область")) is False

    def test_missing_region(self, bf):
        assert bf.matches(make_tender(customer_region=None)) is False

    def test_partial_region_match(self, bf):
        assert bf.matches(make_tender(customer_region="Омская обл")) is True


class TestLaw:
    def test_223fz_allowed(self, bf):
        assert bf.matches(make_tender(law_type="223-fz")) is True

    def test_commercial_rejected(self, bf):
        assert bf.matches(make_tender(law_type="commercial")) is False


class TestNmck:
    def test_below_min(self, bf):
        assert bf.matches(make_tender(nmck=299999)) is False

    def test_above_max(self, bf):
        assert bf.matches(make_tender(nmck=10000001)) is False

    def test_at_bounds(self, bf):
        assert bf.matches(make_tender(nmck=300000)) is True
        assert bf.matches(make_tender(nmck=10000000)) is True

    def test_missing_nmck_rejected(self, bf):
        assert bf.matches(make_tender(nmck=None)) is False


class TestStopWords:
    def test_stop_word_rejects(self, bf):
        t = make_tender(title="Снос и проектирование нового корпуса")
        assert bf.matches(t) is False

    def test_stop_word_case_insensitive(self, bf):
        t = make_tender(
            title="Капитальный ремонт многоквартирных домов, включая демонтаж",
        )
        assert bf.matches(t) is False

    def test_pir_abbreviation(self, bf):
        t = make_tender(title="Демонтаж и ПИР по объекту")
        assert bf.matches(t) is False


class TestLoad:
    def test_load_default_config(self):
        # config/filters.yaml из репозитория должен парситься
        bf = BusinessFilter.load(DEFAULT_CONFIG_PATH)
        assert "омская область" in bf.regions
        assert "44-fz" in bf.laws
        assert bf.nmck_min == 300000
        assert bf.nmck_max == 10000000
        assert "43.11" in bf.okpd2_prefixes
        assert ["снос"] in bf.keywords

    def test_reload_picks_up_changes(self, tmp_path):
        p = tmp_path / "filters.yaml"
        p.write_text("nmck:\n  min: 100\n  max: 200\n", encoding="utf-8")
        bf1 = BusinessFilter.load(str(p))
        assert bf1.nmck_min == 100

        p.write_text("nmck:\n  min: 500\n  max: 900\n", encoding="utf-8")
        bf2 = BusinessFilter.load(str(p))
        assert bf2.nmck_min == 500  # перечитан без рестарта

    def test_empty_config_allows_subject_only(self, tmp_path):
        p = tmp_path / "filters.yaml"
        p.write_text("keywords: ['снос']\n", encoding="utf-8")
        bf = BusinessFilter.load(str(p))
        # регионы/законы не заданы → не ограничивают; НМЦК отсутствует → отказ
        assert bf.matches(make_tender(nmck=None)) is False
        assert bf.matches(make_tender(nmck=1)) is True
