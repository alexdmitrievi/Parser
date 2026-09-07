"""Тесты модуля сбора компаний из 2ГИС (leads.gis2).

Проверяются только чистые функции — построение URL и маппинг карточки 2ГИС в
``LeadCompany``. Оркестрация ``collect_gis2`` требует Chrome и parser-2gis,
поэтому здесь не запускается (покрывается на хосте с браузером).
"""

from __future__ import annotations

from leads.gis2 import (
    Gis2Target,
    _ListWriter,
    build_search_url,
    catalog_item_to_company,
    load_targets,
)

SAMPLE_ITEM = {
    "id": "70000001012345678_f91d4H3777058262347790J0e8g28765",
    "name": "СтанкоПром",
    "name_ex": {"primary": "ООО «СтанкоПром»", "extension": "станки и комплектующие"},
    "org": {"id": "70000001012345678", "name": "СтанкоПром", "branch_count": 1},
    "address_name": "проспект Мира, 25",
    "city_alias": "omsk",
    "adm_div": [
        {"id": "1", "name": "Россия", "type": "country"},
        {"id": "2", "name": "Омская область", "type": "region"},
    ],
    "contact_groups": [
        {
            "name": "Основной",
            "contacts": [
                {"type": "phone", "value": "+7 (3812) 55-66-77", "text": "+7 (3812) 55-66-77"},
                {"type": "email", "value": "sales@stankoprom.ru", "text": "sales@stankoprom.ru"},
                {"type": "website", "value": "http://stankoprom.ru", "url": "http://stankoprom.ru"},
            ],
        }
    ],
    "rubrics": [
        {"id": "614", "name": "Металлообрабатывающее оборудование", "alias": "metalloobrabatyvayushchee-oborudovanie"},
    ],
    "type": "branch",
}


def test_build_search_url_with_rubric():
    url = build_search_url("ru", "omsk", "Металлообрабатывающее оборудование", "614")
    assert url.startswith("https://2gis.ru/omsk/search/")
    assert "/rubricId/614" in url
    assert url.endswith("/filters/sort=name")


def test_build_search_url_without_rubric():
    url = build_search_url("kz", "almaty", "Промышленное оборудование")
    assert url.startswith("https://2gis.kz/almaty/search/")
    assert "/rubricId/" not in url
    assert url.endswith("/filters/sort=name")


def test_catalog_item_to_company_maps_fields():
    company = catalog_item_to_company(SAMPLE_ITEM, country="Russia", profile="industrial_equipment")

    assert company is not None
    assert company.company_name_en == "СтанкоПром"
    assert company.domain == "stankoprom.ru"
    assert company.website == "https://stankoprom.ru"
    assert company.city == "omsk"
    assert company.province == "Омская область"
    assert company.country == "Russia"
    assert company.phones == ["+7 (3812) 55-66-77"]
    assert company.activity == "Металлообрабатывающее оборудование"
    assert company.source_url == "https://2gis.com/firm/70000001012345678"
    assert company.source_name == "2gis"
    assert company.profile == "industrial_equipment"
    assert company.enrich_status == "pending"

    emails = [e.email for e in company.emails]
    assert "sales@stankoprom.ru" in emails
    assert all(e.kind == "role" for e in company.emails)


def test_catalog_item_to_company_falls_back_to_name_ex():
    item = {
        "id": "42_x",
        "name_ex": {"primary": "ТОО «МеталлСервис»"},
        "org": {"name": "МеталлСервис"},
        "city_alias": "almaty",
        "contact_groups": [],
        "rubrics": [],
    }
    company = catalog_item_to_company(item, country="Kazakhstan")
    assert company is not None
    assert company.company_name_en == "ТОО «МеталлСервис»"
    assert company.enrich_status == "no_site"  # нет сайта


def test_catalog_item_to_company_skips_unidentifiable():
    assert catalog_item_to_company({}, country="Russia") is None
    assert catalog_item_to_company({"contact_groups": []}, country="Russia") is None


def test_catalog_item_to_company_ignores_non_company_domain():
    item = dict(SAMPLE_ITEM)
    item["contact_groups"] = [
        {
            "contacts": [
                {"type": "website", "value": "http://facebook.com"},
            ],
        }
    ]
    company = catalog_item_to_company(item, country="Russia")
    assert company is not None
    assert company.domain == ""  # агрегатор не считается сайтом компании
    assert company.enrich_status == "no_site"


def test_list_writer_collects_items():
    sink = []
    writer = _ListWriter(sink)
    writer.write({"result": {"items": [{"id": "1"}, {"id": "2"}]}})
    writer.write({"result": {"items": "не список"}})
    writer.write("не документ")
    assert sink == [{"id": "1"}, {"id": "2"}]


def test_load_targets_reads_yaml(tmp_path):
    yaml_path = tmp_path / "gis2_targets.yaml"
    yaml_path.write_text(
        "profile: industrial_equipment\n"
        "targets:\n"
        "  - country: Russia\n"
        "    city_code: omsk\n"
        "    domain: ru\n"
        "    rubrics:\n"
        "      - {code: '614', name: 'Металлообрабатывающее оборудование'}\n"
        "      - {code: '112', name: 'Промышленное оборудование'}\n",
        encoding="utf-8",
    )

    profile, targets = load_targets(yaml_path)

    assert profile == "industrial_equipment"
    assert len(targets) == 1
    target = targets[0]
    assert isinstance(target, Gis2Target)
    assert target.country == "Russia"
    assert target.city_code == "omsk"
    assert target.domain == "ru"
    assert [r["code"] for r in target.rubrics] == ["614", "112"]
