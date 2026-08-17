"""Домен leads: сбор китайских компаний-импортёров и их контактных почт.

Домен полностью изолирован от tenders и funding и закрыт фиче-флагом
``LEADS_ENABLED`` (по умолчанию false). При выключенном флаге ни одна команда
ничего не делает.

Точка входа — CLI:

    python -m leads collect --profile petcoke_anode
    python -m leads enrich
    python -m leads export --profile petcoke_anode --out leads.csv
    python -m leads stats
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
