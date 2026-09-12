"""Мост leads → CRM: синхронизация компаний в воронку и черновики КП.

Схема CRM живёт в podryad_pro (миграция 057_autoclient_schema.sql):
``crm_leads`` (воронка) → ``outreach_tasks`` (draft → approved → sent)
→ ``lead_messages`` (двусторонняя переписка). Этот модуль — Python-сторона
моста: отбирает обогащённые компании, создаёт CRM-лиды и черновики
email-задач с КП.

КП пишет LLM (Agent Router / glm-5.3), если передан клиент; без LLM
используется детерминированный шаблон. Отправка невозможна до «ОК»
владельца: задачи создаются только со статусом ``draft``, смена статуса
на ``approved`` — вручную владельцем (UI/бот), не этим модулем.
"""

from __future__ import annotations

from typing import Any, Protocol

from engine.observability.logger import get_logger
from leads.models import LeadCompany

logger = get_logger("leads.outreach")

# Черновик КП: язык по стране лида (решение владельца: РФ/КЗ — ru,
# КНР/Турция — en).
_LANGUAGE_BY_COUNTRY = {
    "russia": "ru",
    "россия": "ru",
    "kazakhstan": "ru",
    "казахстан": "ru",
    "china": "en",
    "китай": "en",
    "turkey": "en",
    "турция": "en",
}


class ProposalLLM(Protocol):
    """Минимальный интерфейс LLM для генерации КП."""

    def complete(self, prompt: str) -> str:
        """Вернуть текст по промпту. Формат: ``subject|||body``."""
        ...


def pick_sync_candidates(
    companies: list[LeadCompany], *, profile: str = ""
) -> list[LeadCompany]:
    """Отобрать компании для синхронизации в CRM-воронку.

    Критерии: есть хотя бы один ролевой адрес (рассылка по PIPL/152-ФЗ
    идёт только на ролевые ящики) и совпадение профиля, если задан.

    Args:
        companies: Обогащённые компании.
        profile: Ограничить профилем/кампанией. Пусто — все.

    Returns:
        Компании, годные для первого касания.
    """
    picked = [
        c
        for c in companies
        if c.role_emails and (not profile or c.profile == profile)
    ]
    logger.debug(f"Кандидаты на синхронизацию в CRM: {len(picked)} из {len(companies)}")
    return picked


def _language_for(company: LeadCompany, profile_language: str) -> str:
    """Язык КП: язык страны лида, иначе язык кампании, иначе ru."""
    return _LANGUAGE_BY_COUNTRY.get((company.country or "").strip().lower(), "") or (
        profile_language or "ru"
    )


def build_proposal_context(
    company: LeadCompany, *, profile: Any = None
) -> dict[str, str]:
    """Контекст лида для генерации КП (промпт LLM или шаблон).

    Args:
        company: Обогащённая карточка компании.
        profile: Профиль/кампания (нужен language). ``None`` — дефолты.

    Returns:
        Словарь: name, country, city, activity, offers, requests, email,
        website, language.
    """
    profile_language = getattr(profile, "language", "") if profile else ""
    return {
        "name": company.display_name,
        "country": company.country,
        "city": company.city,
        "activity": company.activity or ", ".join(company.offers[:3]),
        "offers": "; ".join(company.offers[:5]),
        "requests": "; ".join(company.requests[:5]),
        "email": company.role_emails[0].email if company.role_emails else "",
        "website": company.website,
        "language": _language_for(company, profile_language),
    }


def fallback_proposal(company: LeadCompany, *, language: str = "ru") -> tuple[str, str]:
    """Детерминированный шаблон КП без LLM (fallback и база для промпта).

    Args:
        company: Карточка компании.
        language: Язык письма (ru | en).

    Returns:
        Кортеж ``(subject, body)``. Body всегда содержит строку отписки.
    """
    name = company.display_name
    activity = company.activity or ""
    if language == "en":
        subject = f"Cooperation offer for {name}"
        body = (
            f"Hello {name} team,\n\n"
            "We help companies like yours find new B2B customers: targeted lead"
            " generation in your niche and region, with a transparent process and"
            " measurable results.\n"
            + (f"\nWe noticed your profile: {activity}.\n" if activity else "")
            + "\nWould a short call this week work for you to see if there is a fit?\n\n"
            "Best regards,\nPodryad PRO team\n\n"
            "—\nIf you do not wish to receive such emails, reply \"unsubscribe\"."
        )
    else:
        subject = f"Предложение о сотрудничестве — {name}"
        body = (
            f"Здравствуйте, коллеги из «{name}»!\n\n"
            "Помогаем компаниям находить новых B2B-клиентов: лидогенерация под вашу"
            " нишу и гео, прозрачный процесс и измеримый результат.\n"
            + (f"\nМы посмотрели ваш профиль: {activity}.\n" if activity else "")
            + "\nБудет удобно созвониться на этой неделе и понять, есть ли пересечение?\n\n"
            "С уважением,\nкоманда Подряд PRO\n\n"
            "—\nЕсли такие письма не нужны — ответьте «отписать»."
        )
    return subject, body


def _proposal_prompt(context: dict[str, str]) -> str:
    """Промпт для LLM: персонализированное КП по контексту лида."""
    return (
        "Напиши короткое деловое коммерческое предложение (КП) холодного первого"
        " касания на языке '{language}'. Контекст компании-получателя:\n"
        "Название: {name}\nСтрана: {country}\nГород: {city}\n"
        "Деятельность: {activity}\nПредложения: {offers}\nЗапросы: {requests}\n"
        "Мы (Отправитель): агентство «Подряд PRO» — лидогенерация как сервис:"
        " находим B2B-клиентов под нишу и гео заказчика (сбор баз, обогащение,"
        " прогрев, CRM, аналитика).\n"
        "Требования: 3–4 абзаца, конкретика под получателя, без клише, в конце"
        " один вопрос-призыв. Обязательна строка отписки (на языке письма).\n"
        "Верни ровно две строки: сначала тема письма, затем '|||', затем текст."
    ).format(**context)


class CrmBridge:
    """Мост между доменом leads и CRM-схемой podryad_pro."""

    def __init__(self, client: Any, llm: ProposalLLM | None = None):
        self._client = client
        self._llm = llm

    def sync_leads(
        self, companies: list[LeadCompany], *, profile: str = ""
    ) -> int:
        """Создать crm_leads для компаний, которых там ещё нет.

        Args:
            companies: Обогащённые компании.
            profile: Фильтр по профилю/кампании.

        Returns:
            Число созданных CRM-лидов.
        """
        candidates = pick_sync_candidates(companies, profile=profile)
        if not candidates:
            return 0

        # dedup_key → id строки leads_companies (None отбрасываем).
        ids = {
            key: rid
            for key, rid in (
                (self._key_of(c), self._company_row_id(c)) for c in candidates
            )
            if key and rid is not None
        }
        if not ids:
            return 0

        # Компания уже в воронке? (дедуп по company_id)
        existing_ids = self._existing_company_ids(list(ids.values()))
        fresh = [c for c in candidates if ids.get(self._key_of(c)) not in existing_ids]
        if not fresh:
            return 0

        rows = [
            {
                "company_id": ids[self._key_of(company)],
                "niche": company.profile,
                "status": "new",
                "channel": "email",
            }
            for company in fresh
        ]
        rows = [r for r in rows if r["company_id"] is not None]
        if not rows:
            return 0

        self._client.table("crm_leads").insert(rows).execute()
        logger.info(f"CRM: создано лидов {len(rows)}")
        return len(rows)

    @staticmethod
    def _key_of(company: LeadCompany) -> str:
        """dedup_key компании (пустая строка, если нет)."""
        from leads.dedup import company_key

        return company_key(company)

    def _company_row_id(self, company: LeadCompany) -> int | None:
        """Id строки leads_companies (ищем по dedup_key через домен)."""
        from leads.dedup import company_key

        key = company_key(company)
        if not key:
            return None
        result = (
            self._client.table("leads_companies")
            .select("id")
            .eq("dedup_key", key)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return int(rows[0]["id"]) if rows else None

    def _existing_company_ids(self, company_ids: list[int]) -> set[int]:
        """company_id, уже присутствующие в crm_leads."""
        ids = {i for i in company_ids if i is not None}
        if not ids:
            return set()
        result = (
            self._client.table("crm_leads")
            .select("company_id")
            .in_("company_id", list(ids))
            .execute()
        )
        return {int(r["company_id"]) for r in result.data or []}

    def draft_email_tasks(
        self, companies: list[LeadCompany], *, language: str = ""
    ) -> list[dict[str, Any]]:
        """Сгенерировать черновики email-задач (статус draft, без отправки).

        Args:
            companies: Компании с ролевыми адресами.
            language: Язык КП; пусто — по стране лида.

        Returns:
            Список словарей-строк для ``outreach_tasks`` (и они же вставлены).
        """

        tasks: list[dict[str, Any]] = []
        for company in pick_sync_candidates(companies):
            lang = language or _language_for(company, "")
            context = build_proposal_context(company)

            subject, body = fallback_proposal(company, language=lang)
            if self._llm is not None:
                try:
                    answer = self._llm.complete(_proposal_prompt(context))
                    if "|||" in answer:
                        llm_subject, llm_body = answer.split("|||", 1)
                        subject, body = llm_subject.strip(), llm_body.strip()
                except Exception as e:  # noqa: BLE001 - LLM недоступен → шаблон
                    logger.warning(f"LLM недоступен ({e}) — использую шаблон")

            company_id = self._company_row_id(company)
            lead_id = self._lead_id_for_company(company_id) if company_id else None
            if lead_id is None:
                continue

            tasks.append(
                {
                    "lead_id": lead_id,
                    "channel": "email",
                    "status": "draft",
                    "subject": subject,
                    "body": body,
                    "to_address": context["email"],
                }
            )

        if tasks:
            self._client.table("outreach_tasks").insert(tasks).execute()
            logger.info(f"CRM: черновиков КП создано {len(tasks)}")
        return tasks

    def _lead_id_for_company(self, company_id: int) -> int | None:
        """Id crm_leads по company_id (или None, если лида нет)."""
        result = (
            self._client.table("crm_leads")
            .select("id")
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return int(rows[0]["id"]) if rows else None


__all__ = [
    "CrmBridge",
    "ProposalLLM",
    "build_proposal_context",
    "fallback_proposal",
    "pick_sync_candidates",
]
