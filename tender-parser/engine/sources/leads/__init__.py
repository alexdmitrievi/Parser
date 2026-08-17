"""Адаптеры домена leads: каталоги поставщиков, сайты компаний, таможенные данные.

Порядок работы — два шага одного пайплайна, а не независимые прогоны:

1. **Каталоги** (``made_in_china``, ``customs_api``) дают карточки компаний
   и, по возможности, домены их сайтов.
2. **``company_site``** обходит собранные домены и обогащает карточки почтами.

Каждый адаптер включается независимо через ``LEADS_SOURCES``.
"""

from engine.sources.leads.base import LeadsSourceAdapter, SourceUnavailable

__all__ = ["LeadsSourceAdapter", "SourceUnavailable"]
