"""Тесты адаптера каталога zoon.ru (РФ, рубрики по городам).

Проверяются чистые функции: построение URL рубрики, разбор листинга
(ссылки на организации) и разбор детальной страницы (телефон, сайт,
описание). Сетевой обход не выполняется — HTML фикстуры встроены.
"""

from __future__ import annotations

from engine.sources.leads.zoon import (
    BASE_URL,
    ZOON_CITIES,
    ZOON_RUBRICS,
    build_rubric_url,
    extract_org_links,
    parse_org_page,
)


LISTING_HTML = """
<html><body>
<div class="catalog-organizations">
  <a href="https://zoon.ru/omsk/building/kompaniya_metalloprokata_brinell/">Компания металлопроката Бринелль</a>
  <a href="https://zoon.ru/omsk/building/avarijno-servisnaya_sluzhba_dvernoj_doktor_na_ulitse_70_let_oktyabrya-d854/">Дверной доктор</a>
  <a href="https://zoon.ru/omsk/building/type/remont_kvartir/">Ремонт квартир (рубрика)</a>
  <a href="https://zoon.ru/omsk/building/bratya_green/price/">Братья Грин прайс</a>
</div>
</body></html>
"""

ORG_HTML = """
<html><body>
<span itemprop="name">Компания металлопроката Бринелль</span>
<span itemprop="streetAddress">ул Омская, д 194</span>
<meta itemprop="addressLocality" content="Омск"/>
Адрес компании: Россия, Омская обл, Омск, ул Омская, д 194.
Позвоните по номеру +7 (3812) 78-02-88 или посетите сайт omsk.brinelle.ru.
</body></html>
"""

ORG_HTML_JSON = """
<html><body>
<script>
{"photos":[{"source":"Фото взято с сайта \\u003Ca rel=\\"nofollow\\" href=\\"https:\\/\\/omsk.brinelle.ru\\"\\u003Eomsk.brinelle.ru\\u003C\\/a\\u003E"}]}
</script>
</body></html>
"""


class TestBuildRubricUrl:
    def test_city_and_rubric(self):
        url = build_rubric_url("omsk", "building")
        assert url == f"{BASE_URL}/omsk/building/"

    def test_city_normalized(self):
        assert "/msk/building/" in build_rubric_url("MSK", "building")


class TestExtractOrgLinks:
    def test_extracts_org_pages_only(self):
        links = extract_org_links(LISTING_HTML, base=f"{BASE_URL}/omsk/building/")
        # type/ и price/ — не организации;(org-slug без /type|/price)
        assert len(links) == 2
        assert links[0].endswith("/omsk/building/kompaniya_metalloprokata_brinell/")

    def test_dedupes(self):
        html = LISTING_HTML + LISTING_HTML
        links = extract_org_links(html, base=f"{BASE_URL}/omsk/building/")
        assert len(links) == 2


class TestParseOrgPage:
    def test_phone_site_address(self):
        info = parse_org_page(ORG_HTML)
        assert info["phone"] == "+7 (3812) 78-02-88"
        assert info["address"].startswith("ул Омская")
        assert info["city"] == "Омск"

    def test_site_from_json_photo_source(self):
        html = ORG_HTML + ORG_HTML_JSON
        info = parse_org_page(html)
        assert info["site"] == "https://omsk.brinelle.ru"

    def test_site_from_text_mention(self):
        info = parse_org_page(ORG_HTML)
        assert info["site"].endswith("omsk.brinelle.ru")

    def test_empty_page(self):
        info = parse_org_page("<html></html>")
        assert info["phone"] == ""
        assert info["site"] == ""


class TestRubricCatalog:
    def test_rubrics_nonempty(self):
        assert "building" in ZOON_RUBRICS

    def test_cities_contain_rf_majors(self):
        assert "omsk" in ZOON_CITIES
        assert "msk" in ZOON_CITIES or "moscow" in ZOON_CITIES
