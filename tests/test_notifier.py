"""Tests for subscription matching logic in pipeline/notifier.py."""
import pytest


def _matches_subscription(tender, sub):
    """Copy of notifier._matches_subscription for isolated testing."""
    sub_niches = sub.get("niche_tags") or []
    tender_niches = tender.get("niche_tags") or []
    if sub_niches and not set(sub_niches) & set(tender_niches):
        return False

    sub_keywords = sub.get("keywords") or []
    if sub_keywords:
        text = f"{tender.get('title', '')} {tender.get('description', '')}".lower()
        if not any(kw.lower() in text for kw in sub_keywords):
            return False

    sub_regions = sub.get("regions") or []
    if sub_regions:
        tender_region = tender.get("customer_region", "")
        if tender_region and not any(r.lower() in tender_region.lower() for r in sub_regions):
            return False

    tender_nmck = tender.get("nmck")
    if tender_nmck is not None:
        min_nmck = sub.get("min_nmck")
        max_nmck = sub.get("max_nmck")
        if min_nmck is not None and tender_nmck < min_nmck:
            return False
        if max_nmck is not None and tender_nmck > max_nmck:
            return False

    sub_okpd2 = sub.get("okpd2_prefixes") or []
    tender_okpd2 = tender.get("okpd2_codes") or []
    if sub_okpd2 and tender_okpd2:
        matched = any(
            code.startswith(prefix)
            for code in tender_okpd2
            for prefix in sub_okpd2
        )
        if not matched:
            return False

    sub_laws = sub.get("law_types") or []
    if sub_laws and tender.get("law_type") not in sub_laws:
        return False

    return True


class TestMatchesSubscription:
    def test_empty_subscription_matches_everything(self):
        tender = {"title": "Test", "niche_tags": []}
        sub = {}
        assert _matches_subscription(tender, sub) is True

    def test_niche_match(self):
        tender = {"title": "Ремонт", "niche_tags": ["construction"]}
        sub = {"niche_tags": ["construction"]}
        assert _matches_subscription(tender, sub) is True

    def test_niche_no_match(self):
        tender = {"title": "Мебель", "niche_tags": ["furniture"]}
        sub = {"niche_tags": ["construction"]}
        assert _matches_subscription(tender, sub) is False

    def test_niche_intersection(self):
        tender = {"title": "Test", "niche_tags": ["construction", "furniture"]}
        sub = {"niche_tags": ["construction", "it"]}
        assert _matches_subscription(tender, sub) is True

    def test_keyword_match_in_title(self):
        tender = {"title": "Капитальный ремонт кровли", "description": ""}
        sub = {"keywords": ["ремонт"]}
        assert _matches_subscription(tender, sub) is True

    def test_keyword_match_in_description(self):
        tender = {"title": "Закупка", "description": "Требуется ремонт помещений"}
        sub = {"keywords": ["ремонт"]}
        assert _matches_subscription(tender, sub) is True

    def test_keyword_no_match(self):
        tender = {"title": "Поставка мебели", "description": ""}
        sub = {"keywords": ["ремонт", "кровля"]}
        assert _matches_subscription(tender, sub) is False

    def test_keyword_case_insensitive(self):
        tender = {"title": "РЕМОНТ КРОВЛИ", "description": ""}
        sub = {"keywords": ["ремонт"]}
        assert _matches_subscription(tender, sub) is True

    def test_region_exact_match(self):
        tender = {"customer_region": "Омская область"}
        sub = {"regions": ["Омская область"]}
        assert _matches_subscription(tender, sub) is True

    def test_region_partial_match(self):
        tender = {"customer_region": "Омская область"}
        sub = {"regions": ["Омск"]}
        assert _matches_subscription(tender, sub) is True

    def test_region_no_match(self):
        tender = {"customer_region": "Омская область"}
        sub = {"regions": ["Москва"]}
        assert _matches_subscription(tender, sub) is False

    def test_nmck_in_range(self):
        tender = {"nmck": 5000000}
        sub = {"min_nmck": 1000000, "max_nmck": 10000000}
        assert _matches_subscription(tender, sub) is True

    def test_nmck_below_min(self):
        tender = {"nmck": 500000}
        sub = {"min_nmck": 1000000, "max_nmck": 10000000}
        assert _matches_subscription(tender, sub) is False

    def test_nmck_above_max(self):
        tender = {"nmck": 15000000}
        sub = {"min_nmck": 1000000, "max_nmck": 10000000}
        assert _matches_subscription(tender, sub) is False

    def test_nmck_only_min(self):
        tender = {"nmck": 5000000}
        sub = {"min_nmck": 1000000}
        assert _matches_subscription(tender, sub) is True

    def test_nmck_only_max(self):
        tender = {"nmck": 5000000}
        sub = {"max_nmck": 10000000}
        assert _matches_subscription(tender, sub) is True

    def test_nmck_none_in_tender_skipped(self):
        tender = {"nmck": None, "title": "Test"}
        sub = {"min_nmck": 1000000, "max_nmck": 10000000}
        assert _matches_subscription(tender, sub) is True

    def test_okpd2_prefix_match(self):
        tender = {"title": "Test", "okpd2_codes": ["43.91.19.110"]}
        sub = {"okpd2_prefixes": ["43.9"]}
        assert _matches_subscription(tender, sub) is True

    def test_okpd2_prefix_no_match(self):
        tender = {"title": "Test", "okpd2_codes": ["43.91.19.110"]}
        sub = {"okpd2_prefixes": ["31.0"]}
        assert _matches_subscription(tender, sub) is False

    def test_okpd2_empty_tender_skips(self):
        tender = {"title": "Test", "okpd2_codes": []}
        sub = {"okpd2_prefixes": ["43.9"]}
        assert _matches_subscription(tender, sub) is True

    def test_law_type_match(self):
        tender = {"title": "Test", "law_type": "44-fz"}
        sub = {"law_types": ["44-fz"]}
        assert _matches_subscription(tender, sub) is True

    def test_law_type_no_match(self):
        tender = {"title": "Test", "law_type": "223-fz"}
        sub = {"law_types": ["44-fz"]}
        assert _matches_subscription(tender, sub) is False

    def test_combined_match(self):
        tender = {
            "title": "Капитальный ремонт кровли",
            "description": "Работы по замене кровли",
            "customer_region": "Москва",
            "nmck": 5800000,
            "niche_tags": ["construction"],
            "okpd2_codes": ["43.91.19.110"],
            "law_type": "44-fz",
        }
        sub = {
            "niche_tags": ["construction"],
            "keywords": ["ремонт"],
            "regions": ["Москва"],
            "min_nmck": 1000000,
            "max_nmck": 10000000,
            "okpd2_prefixes": ["43.9"],
            "law_types": ["44-fz"],
        }
        assert _matches_subscription(tender, sub) is True

    def test_combined_one_mismatch_fails(self):
        tender = {
            "title": "Ремонт дороги",
            "customer_region": "Омская область",
            "nmck": 500000,
            "niche_tags": ["construction"],
            "law_type": "44-fz",
        }
        sub = {
            "niche_tags": ["construction"],
            "regions": ["Москва"],
            "law_types": ["44-fz"],
        }
        assert _matches_subscription(tender, sub) is False
