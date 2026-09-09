"""Тесты скоринга теплоты лидов (cold/warm/hot)."""

from __future__ import annotations

from leads.models import LeadCompany, LeadEmail
from leads.scoring import (
    HEAT_COLD,
    HEAT_HOT,
    HEAT_WARM,
    canonical_country,
    country_matches,
    heat_breakdown,
    heat_from_score,
    score_heat,
)


def _company(**kwargs) -> LeadCompany:
    return LeadCompany(**kwargs)


class TestThresholds:
    def test_score_boundaries(self):
        assert heat_from_score(0) == HEAT_COLD
        assert heat_from_score(29) == HEAT_COLD
        assert heat_from_score(30) == HEAT_WARM
        assert heat_from_score(59) == HEAT_WARM
        assert heat_from_score(60) == HEAT_HOT

    def test_score_is_monotonic(self):
        assert heat_from_score(10) == HEAT_COLD
        assert heat_from_score(45) == HEAT_WARM
        assert heat_from_score(99) == HEAT_HOT


class TestScoring:
    def test_empty_company_is_cold(self):
        assert score_heat(_company()).heat == HEAT_COLD

    def test_role_email_only_is_warm(self):
        company = _company(emails=[LeadEmail(email="info@acme.cn")])
        heat = score_heat(company)
        assert heat.heat == HEAT_WARM
        assert heat.score == 40

    def test_full_signals_is_hot(self):
        company = _company(
            company_name_en="ACME Tools",
            website="https://acme.cn",
            emails=[LeadEmail(email="sales@acme.cn")],
            phones=["+8613800000000"],
            wechat="acme_tools",
            matched_keywords=["cnc machine"],
            country="China",
            offers=["cnc machines", "milling machines"],
            industry_guess="machine tools",
        )
        heat = score_heat(company, countries={"china"})
        assert heat.heat == HEAT_HOT
        assert "role_email" in heat.reasons
        assert "geo_match" in heat.reasons

    def test_geo_bonus_counts_only_when_target_set(self):
        company = _company(country="Russia")
        assert score_heat(company).score == 0
        assert score_heat(company, countries={"Russia"}).score == 15

    def test_personal_email_scores_less_than_role(self):
        role = _company(emails=[LeadEmail(email="sales@acme.cn", kind="role")])
        personal = _company(emails=[LeadEmail(email="li.wei@acme.cn", kind="personal")])
        assert score_heat(role).score > score_heat(personal).score


class TestCountryNormalization:
    def test_canonical_aliases(self):
        assert canonical_country("Россия") == "russia"
        assert canonical_country("россия") == "russia"
        assert canonical_country("Казахстан") == "kazakhstan"
        assert canonical_country("China") == "china"

    def test_country_matches_with_aliases(self):
        assert country_matches("Россия", {"Russia", "Kazakhstan"})
        assert country_matches("Казахстан", {"Russia", "Kazakhstan"})
        assert not country_matches("China", {"Russia", "Kazakhstan"})
        assert not country_matches("", {"Russia"})

    def test_country_matches_empty_target(self):
        assert not country_matches("Russia", set())


class TestBreakdown:
    def test_breakdown_counts_each_heat(self):
        companies = [
            _company(),                                              # cold
            _company(emails=[LeadEmail(email="info@a.cn")]),         # warm
            _company(
                website="https://b.cn",
                emails=[LeadEmail(email="sales@b.cn")],
                phones=["+86"],
                matched_keywords=["cnc"],
                country="China",
                industry_guess="tools",
            ),                                                      # hot
        ]
        breakdown = heat_breakdown(companies, countries={"China"})
        assert breakdown[HEAT_COLD] == 1
        assert breakdown[HEAT_WARM] == 1
        assert breakdown[HEAT_HOT] == 1
