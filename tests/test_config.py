"""Tests for config parsing, rate limiter logic, and time utilities."""
import os
import sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TestConfig:
    def test_supabase_url_env(self):
        from shared.config import get_config
        cfg = get_config()
        assert isinstance(cfg, dict)
        assert "supabase_url" in cfg
        assert "supabase_key" in cfg
        assert "telegram_bot_token" in cfg
        assert "max_free_subscriptions" in cfg

    def test_max_free_subscriptions_default(self):
        from shared.config import get_config
        cfg = get_config()
        max_subs = cfg.get("max_free_subscriptions", 3)
        assert 1 <= max_subs <= 100

    def test_safe_int(self):
        from shared.config import _safe_int
        assert _safe_int("5", 3) == 5
        assert _safe_int("abc", 3) == 3
        assert _safe_int("", 3) == 3
        assert _safe_int("0", 5) == 0

    def test_niche_presets(self):
        from shared.config import NICHE_FURNITURE, NICHE_CONSTRUCTION, ALL_NICHES
        assert NICHE_FURNITURE.name == "Мебель"
        assert NICHE_FURNITURE.tag == "furniture"
        assert "мебель" in NICHE_FURNITURE.keywords
        assert "31.0" in NICHE_FURNITURE.okpd2_prefixes

        assert NICHE_CONSTRUCTION.name == "Строительство"
        assert NICHE_CONSTRUCTION.tag == "construction"
        assert "подряд" in NICHE_CONSTRUCTION.keywords
        assert "41.2" in NICHE_CONSTRUCTION.okpd2_prefixes

        # Ниш стало больше двух — проверяем состав, а не жёсткое число,
        # чтобы добавление ниши не роняло тест.
        tags = [n.tag for n in ALL_NICHES]
        assert {"furniture", "construction"} <= set(tags)
        assert len(tags) == len(set(tags)), "теги ниш должны быть уникальны"
        assert all(n.name and n.keywords and n.okpd2_prefixes for n in ALL_NICHES)


class TestRateLimiter:
    def test_rate_limit_exists(self):
        from shared.rate_limiter import rate_limit_middleware
        assert callable(rate_limit_middleware)

    def test_rate_limit_initialization(self):
        from shared.rate_limiter import rate_limit_middleware
        import inspect
        sig = inspect.signature(rate_limit_middleware)
        assert len(sig.parameters) >= 1


class TestConstants:
    def test_russian_regions(self):
        from shared.constants import RUSSIAN_REGIONS
        assert len(RUSSIAN_REGIONS) >= 80
        assert "Москва" in RUSSIAN_REGIONS
        assert "Омская область" in RUSSIAN_REGIONS

    def test_platforms(self):
        from shared.constants import PLATFORMS
        assert "eis" in PLATFORMS
        assert "b2b_center" in PLATFORMS
        assert isinstance(PLATFORMS["eis"], dict)

    def test_purchase_methods(self):
        from shared.constants import PURCHASE_METHODS
        assert len(PURCHASE_METHODS) >= 4
        assert "AE" in PURCHASE_METHODS
        assert "OK" in PURCHASE_METHODS


class TestTimeUtils:
    def test_now_utc(self):
        from shared.time_utils import now_utc
        now = now_utc()
        assert now is not None

    def test_parse_datetime_ru(self):
        from shared.time_utils import parse_datetime_ru
        result = parse_datetime_ru("2026-01-15T00:00:00")
        assert result is not None


class TestRussianStemmer:
    def test_stem_russian_exists(self):
        from shared.db import _stem_russian
        assert callable(_stem_russian)

    def test_stem_typical_endings(self):
        from shared.db import _stem_russian
        stem1 = _stem_russian("ремонта")
        assert len(stem1) < 7
        stem2 = _stem_russian("кровли")
        assert len(stem2) < 6
        stem3 = _stem_russian("строительные")
        assert len(stem3) < 11

    def test_stem_short_words(self):
        from shared.db import _stem_russian
        result = _stem_russian("да")
        assert isinstance(result, str)
