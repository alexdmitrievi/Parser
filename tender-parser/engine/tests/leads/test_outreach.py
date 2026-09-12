"""Тесты моста leads → CRM (leads.outreach).

Проверяются чистые функции: выбор компаний для синхронизации в CRM,
построение контекста для КП, детерминированный шаблон КП (fallback без
LLM) и генерация черновиков задач рассылки. Сетевые вызовы (Agent Router)
и запись в Supabase мокаются.
"""

from __future__ import annotations

from typing import Any

from leads.models import LeadCompany, LeadEmail
from leads.outreach import (
    CrmBridge,
    build_proposal_context,
    fallback_proposal,
    pick_sync_candidates,
)
from leads.profiles import Profile


def _company(**kwargs) -> LeadCompany:
    defaults = dict(
        company_name_en="ООО СтанкоПром",
        domain="stankoprom.ru",
        country="Russia",
        city="Омск",
        activity="Металлообрабатывающее оборудование, станки",
        emails=[LeadEmail(email="info@stankoprom.ru", kind="role")],
        profile="industrial_equipment",
    )
    defaults.update(kwargs)
    return LeadCompany(**defaults)


class TestPickSyncCandidates:
    def test_only_with_role_emails(self):
        with_mail = _company()
        no_mail = _company(emails=[], domain="x.ru")
        personal_only = _company(
            emails=[LeadEmail(email="ivan@stankoprom.ru", kind="personal")],
            domain="y.ru",
        )
        picked = pick_sync_candidates([with_mail, no_mail, personal_only])
        assert picked == [with_mail]

    def test_profile_filter(self):
        a = _company()
        b = _company(profile="other", domain="z.ru")
        picked = pick_sync_candidates([a, b], profile="industrial_equipment")
        assert picked == [a]


class TestBuildContext:
    def test_context_fields(self):
        context = build_proposal_context(_company())
        assert context["name"] == "ООО СтанкоПром"
        assert context["country"] == "Russia"
        assert context["email"] == "info@stankoprom.ru"
        assert "станки" in context["activity"].lower()

    def test_language_from_profile(self):
        profile = Profile(name="p", language="en", countries=["China"])
        context = build_proposal_context(_company(country="China"), profile=profile)
        assert context["language"] == "en"


class TestFallbackProposal:
    def test_ru_proposal(self):
        company = _company()
        subject, body = fallback_proposal(company, language="ru")
        assert "СтанкоПром" in subject or "СтанкоПром" in body
        assert "отпис" in body.lower()  # обязательная строка отписки

    def test_en_proposal(self):
        company = _company(company_name_en="StankoProm LLC")
        subject, body = fallback_proposal(company, language="en")
        assert "StankoProm" in body
        assert "unsubscribe" in body.lower()


class FakeQueryClient:
    """Мок supabase-клиента: цепочка запросов + вставки, lookups по таблицам."""

    def __init__(self):
        self.inserted: dict[str, list[dict]] = {}
        # id, возвращаемый lookup'ом leads_companies; crm_leads lookups пусты.
        self.company_row = {"id": 1, "company_id": 1}
        self.lead_row: dict | None = None  # None → лида нет; dict → есть

    def table(self, name: str):
        client = self

        class _Q:
            _chain: list[tuple[str, Any]] = []

            def select(self, *a):
                return self

            def eq(self, col, val):
                return self

            def in_(self, col, vals):
                return self

            def limit(self, n):
                return self

            def execute(self):
                class R:
                    data: list = []

                if name == "leads_companies":
                    R.data = [client.company_row]
                elif name == "crm_leads" and client.lead_row is not None:
                    R.data = [client.lead_row]
                return R()

            def insert(self, rows):
                client.inserted.setdefault(name, []).extend(
                    rows if isinstance(rows, list) else [rows]
                )
                return self

        return _Q()


class FakeLLM:
    def complete(self, prompt: str) -> str:
        return "LLM-SUBJECT|||LLM-BODY"


class TestCrmBridge:
    def test_sync_creates_crm_leads(self):
        client = FakeQueryClient()
        bridge = CrmBridge(client=client, llm=None)

        inserted = bridge.sync_leads([_company()])
        assert inserted == 1
        row = client.inserted["crm_leads"][0]
        assert row["company_id"] == 1
        assert row["status"] == "new"
        assert row["niche"] == "industrial_equipment"

    def test_draft_uses_llm_when_available(self):
        client = FakeQueryClient()
        client.lead_row = {"id": 7}
        bridge = CrmBridge(client=client, llm=FakeLLM())
        tasks = bridge.draft_email_tasks([_company()])
        assert len(tasks) == 1
        assert tasks[0]["subject"] == "LLM-SUBJECT"
        assert tasks[0]["status"] == "draft"
        assert tasks[0]["to_address"] == "info@stankoprom.ru"

    def test_draft_falls_back_without_llm(self):
        client = FakeQueryClient()
        client.lead_row = {"id": 7}
        bridge = CrmBridge(client=client, llm=None)
        tasks = bridge.draft_email_tasks([_company()], language="ru")
        assert len(tasks) == 1
        assert tasks[0]["status"] == "draft"
        assert "отпис" in tasks[0]["body"].lower()
