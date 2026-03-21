"""Константы: регионы, площадки, маппинги."""

# Популярные регионы для inline-кнопок бота
POPULAR_REGIONS = [
    "Москва",
    "Санкт-Петербург",
    "Омская область",
    "Новосибирская область",
    "Тюменская область",
    "Свердловская область",
    "Краснодарский край",
    "Республика Татарстан",
]

# Маппинг площадок
PLATFORMS = {
    "eis": {"name": "ЕИС (zakupki.gov.ru)", "url": "https://zakupki.gov.ru"},
    "sberbank_ast": {"name": "Сбербанк-АСТ", "url": "https://sberbank-ast.ru"},
    "rts_tender": {"name": "РТС-тендер", "url": "https://rts-tender.ru"},
    "roseltorg": {"name": "Росэлторг", "url": "https://roseltorg.ru"},
    "b2b_center": {"name": "B2B-Center", "url": "https://b2b-center.ru"},
    "fabrikant": {"name": "Fabrikant", "url": "https://fabrikant.ru"},
    "tenderpro": {"name": "TenderPro", "url": "https://tenderpro.ru"},
    "tenderguru": {"name": "TenderGuru", "url": "https://tenderguru.ru"},
    "tektorg": {"name": "ТЭК-Торг", "url": "https://tektorg.ru"},
    "etpgpb": {"name": "ЭТП ГПБ", "url": "https://etpgpb.ru"},
}

# Способы закупки
PURCHASE_METHODS = {
    "AE": "Электронный аукцион",
    "OK": "Открытый конкурс",
    "ZK": "Запрос котировок",
    "ZP": "Запрос предложений",
    "EP": "Единственный поставщик",
    "OA": "Открытый аукцион",
}

# Типы закона
LAW_TYPES = {
    "44-fz": "44-ФЗ",
    "223-fz": "223-ФЗ",
    "commercial": "Коммерческий",
    "pp615": "ПП РФ 615",
}

# Диапазоны НМЦК для фильтров бота
NMCK_RANGES = {
    "до 500К": (0, 500_000),
    "500К — 5М": (500_000, 5_000_000),
    "5М — 50М": (5_000_000, 50_000_000),
    "50М+": (50_000_000, None),
    "Любая": (None, None),
}

# Регион-коды ЕИС FTP (основные)
EIS_REGION_CODES = {
    "Altaj_Resp": "Республика Алтай",
    "Bashkortostan_Resp": "Республика Башкортостан",
    "Krasnodarskij_kraj": "Краснодарский край",
    "Krasnoyarskij_kraj": "Красноярский край",
    "Moskva": "Москва",
    "Moskovskaya_obl": "Московская область",
    "Novosibirskaya_obl": "Новосибирская область",
    "Omskaya_obl": "Омская область",
    "Sankt-Peterburg": "Санкт-Петербург",
    "Sverdlovskaya_obl": "Свердловская область",
    "Tatarstan_Resp": "Республика Татарстан",
    "Tyumenskaya_obl": "Тюменская область",
}
