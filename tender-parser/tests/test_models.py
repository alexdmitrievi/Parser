"""Tests for Pydantic models in shared/models.py."""
import pytest
from shared.models import (
    TenderCreate, SubscriptionCreate, SearchFilters,
    FundingProgramCreate, FundingSearchFilters,
)


class TestTenderCreate:
    def test_minimal_valid(self):
        t = TenderCreate(source_platform="eis", title="Ремонт крыши")
        assert t.source_platform == "eis"
        assert t.title == "Ремонт крыши"
        assert t.status == "active"

    def test_full_fields(self, sample_tender_dict):
        t = TenderCreate(**sample_tender_dict)
        assert t.nmck == 5800000.00
        assert t.law_type == "44-fz"
        assert t.niche_tags == ["construction"]

    def test_optional_fields_default(self):
        t = TenderCreate(source_platform="b2b_center", title="Test")
        assert t.description is None
        assert t.nmck is None
        assert t.law_type is None
        assert t.status == "active"
        assert t.okpd2_codes == []
        assert t.niche_tags == []

    def test_sources_default(self):
        t = TenderCreate(source_platform="eis", title="Test")
        assert t.sources == []

    def test_model_dump_json(self, sample_tender_dict):
        t = TenderCreate(**sample_tender_dict)
        d = t.model_dump(mode="json")
        assert d["source_platform"] == "eis"
        assert d["nmck"] == 5800000.00
        assert isinstance(d["publish_date"], str)


class TestSearchFilters:
    def test_defaults(self):
        f = SearchFilters()
        assert f.page == 1
        assert f.per_page == 5
        assert f.sort_by == "created_at"
        assert f.query is None
        assert f.region is None

    def test_from_state_dict_basic(self, sample_search_filters_dict):
        f = SearchFilters.from_state_dict(sample_search_filters_dict, page=1)
        assert f.query == "ремонт кровли"
        assert f.region == "Москва"
        assert f.niche == "construction"
        assert f.min_nmck == 1000000
        assert f.max_nmck == 10000000

    def test_from_state_dict_aliases(self):
        f = SearchFilters.from_state_dict({"law": "44-fz"}, page=1)
        assert f.law_type == "44-fz"

        f2 = SearchFilters.from_state_dict({"law_type": "223-fz"}, page=1)
        assert f2.law_type == "223-fz"

    def test_from_state_dict_empty(self):
        f = SearchFilters.from_state_dict({}, page=1)
        assert f.page == 1
        assert f.per_page == 5

    def test_from_state_dict_page_override(self):
        f = SearchFilters.from_state_dict({"query": "test"}, page=3, per_page=20)
        assert f.page == 3
        assert f.per_page == 20
        assert f.query == "test"

    def test_date_filters(self):
        f = SearchFilters.from_state_dict(
            {"date_from": "2026-01-01", "date_to": "2026-06-30"}, page=1
        )
        assert f.date_from == "2026-01-01"
        assert f.date_to == "2026-06-30"

    def test_sort_validation(self):
        f = SearchFilters.from_state_dict({"sort": "deadline"}, page=1)
        assert f.sort_by == "deadline"
        f2 = SearchFilters.from_state_dict({"sort": "nmck"}, page=1)
        assert f2.sort_by == "nmck"
        f3 = SearchFilters.from_state_dict({"sort": "publish_date"}, page=1)
        assert f3.sort_by == "publish_date"


class TestSubscriptionCreate:
    def test_minimal(self):
        s = SubscriptionCreate(telegram_user_id=123, name="test_user")
        assert s.telegram_user_id == 123
        assert s.name == "test_user"
        assert s.keywords == []
        assert s.regions == []
        assert s.niche_tags == []

    def test_full(self, sample_subscription_dict):
        s = SubscriptionCreate(**sample_subscription_dict)
        assert s.keywords == ["ремонт", "кровля"]
        assert s.regions == ["Москва"]
        assert s.min_nmck == 1000000
        assert s.max_nmck == 10000000

    def test_empty_arrays_default(self):
        s = SubscriptionCreate(telegram_user_id=456, name="user")
        assert s.keywords == []
        assert s.regions == []
        assert s.niche_tags == []
        assert s.law_types == []
        assert s.okpd2_prefixes == []


class TestFundingProgramCreate:
    def test_minimal(self):
        f = FundingProgramCreate(
            source_platform="corpmsp",
            program_name="Льготный кредит 1764",
            program_type="loan",
            original_url="https://corpmsp.ru/program",
        )
        assert f.source_platform == "corpmsp"
        assert f.program_type == "loan"
        assert f.status == "active"

    def test_full(self):
        f = FundingProgramCreate(
            source_platform="frprf",
            program_name="Займ на развитие производства",
            program_type="loan",
            original_url="https://frprf.ru/program",
            amount_min=50000000,
            amount_max=2000000000,
            rate=1.0,
            term_months=60,
            regions=["Вся Россия"],
            industries=["Промышленность"],
            status="active",
        )
        assert f.amount_min == 50000000
        assert f.amount_max == 2000000000
        assert f.rate == 1.0
        assert f.term_months == 60

    def test_program_type_variants(self):
        for ptype in ["grant", "loan", "microloan", "subsidy", "guarantee", "compensation", "leasing"]:
            f = FundingProgramCreate(
                source_platform="mybusiness",
                program_name="Test",
                program_type=ptype,
                original_url="https://example.com",
            )
            assert f.program_type == ptype


class TestFundingSearchFilters:
    def test_defaults(self):
        f = FundingSearchFilters()
        assert f.page == 1
        assert f.per_page == 12
        assert f.status == "active"

    def test_filters(self):
        f = FundingSearchFilters(
            query="грант", program_type="grant",
            region="Москва",
            amount_max=1000000, page=2, per_page=20,
        )
        assert f.program_type == "grant"
        assert f.region == "Москва"
        assert f.amount_max == 1000000
        assert f.page == 2
        assert f.per_page == 20
