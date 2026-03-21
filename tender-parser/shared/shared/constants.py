"""Площадки и справочники для парсеров и API."""

PLATFORMS: dict[str, dict[str, str]] = {
    "eis": {"name": "ЕИС (zakupki.gov.ru)", "law": "44/223"},
    "b2b_center": {"name": "B2B-Center", "law": "commercial"},
    "fabrikant": {"name": "Фабрикант (fabrikant.ru)", "law": "commercial"},
    "etpgpb": {"name": "ЭТП ГПБ (etpgpb.ru)", "law": "223-fz"},
    "etp_ets": {"name": "НЭП (etp-ets.ru)", "law": "44/223"},
    "tenderpro": {"name": "TenderPro", "law": "commercial"},
    "lot_online": {"name": "РАД / lot-online.ru", "law": "44-fz"},
    "zakupki_mos": {"name": "Портал закупок Москвы", "law": "regional"},
    "tektorg": {"name": "Текторг", "law": "223-fz"},
}

PRIMARY_SOURCE_PRIORITY = ("eis", "etp_ets", "etpgpb", "lot_online", "zakupki_mos")
