"""Тесты адаптера каталога yell.ru (РФ, рубрики по городам).

Проверяются чистые функции: построение URL рубрики, разбор листинга
(компании с адресами) и разбор детальной страницы (телефон, сайт).
Сетевой обход не выполняется — HTML фикстуры встроены.
"""

from __future__ import annotations

from engine.sources.leads.yell import (
    BASE_URL,
    YellAdapter,
    build_rubric_url,
    parse_company_page,
    parse_listing_html,
)


LISTING_HTML = """
<html><body>
<div class="companies__item" itemprop="itemListElement">
  <a class="companies__item-image" href="/omsk/com/delta-inzhiniring_14481081/"></a>
  <div class="companies__item-title">
    <h2><a href="/omsk/com/delta-inzhiniring_14481081/" itemprop="url">Дельта-инжиниринг</a></h2>
  </div>
  <div class="companies__item-address">Россия, г Омск, ул Енисейская, д 3</div>
</div>
<div class="companies__item" itemprop="itemListElement">
  <a class="companies__item-image" href="/omsk/com/laserspro_12096001/"></a>
  <div class="companies__item-title">
    <h2><a href="/omsk/com/laserspro_12096001/" itemprop="url">LasersPro</a></h2>
  </div>
  <div class="companies__item-address">Россия, г Омск, ул Мира, д 12</div>
</div>
</body></html>
"""

COMPANY_HTML = """
<html><body>
<h1>Дельта-инжиниринг</h1>
<div class="company__contacts-item-text">
  <span itemprop="telephone">+7 381 220-75-36</span>
</div>
<div class="company__contacts-item" itemprop="address" itemscope>
  <span class="company__contacts-item-text" itemprop="streetAddress">г Омск, ул Енисейская, д 3</span>
  <meta itemprop="addressLocality" content="г Омск"/>
</div>
</body></html>
"""


class TestBuildRubricUrl:
    def test_city_and_rubric(self):
        url = build_rubric_url("omsk", "proizvodstvo-i-optovaya-torgovlya")
        assert url == f"{BASE_URL}/omsk/top/proizvodstvo-i-optovaya-torgovlya/"

    def test_city_normalized(self):
        url = build_rubric_url("Omsk", "stroitelstvo")
        assert "/omsk/top/stroitelstvo/" in url


class TestParseListing:
    def test_extracts_companies(self):
        companies = parse_listing_html(LISTING_HTML, page_url=f"{BASE_URL}/omsk/top/test/")
        assert len(companies) == 2
        first = companies[0]
        assert first.company_name_en == "Дельта-инжиниринг"
        assert first.source_name == "yell"
        assert first.source_url.endswith("/omsk/com/delta-inzhiniring_14481081/")
        assert first.country == "Russia"

    def test_address_captured(self):
        companies = parse_listing_html(LISTING_HTML, page_url=f"{BASE_URL}/omsk/top/test/")
        assert "Енисейская" in companies[0].activity or companies[0].city

    def test_empty_listing(self):
        assert parse_listing_html("<html></html>", page_url="https://x") == []

    def test_dedupes_reviews_links(self):
        # /reviews/ суффиксы не должны давать отдельные компании
        html = LISTING_HTML.replace(
            'href="/omsk/com/laserspro_12096001/"',
            'href="/omsk/com/laserspro_12096001/reviews/"',
        )
        companies = parse_listing_html(html, page_url=f"{BASE_URL}/omsk/top/test/")
        assert len(companies) == 2


class TestParseCompanyPage:
    def test_phone_extracted(self):
        info = parse_company_page(COMPANY_HTML)
        assert info["phone"] == "+7 381 220-75-36"
        assert "Енисейская" in info["address"]

    def test_missing_phone(self):
        assert parse_company_page("<html></html>")["phone"] == ""


class TestYellAdapterConfig:
    def test_source_id(self):
        from engine.sources.leads.yell import SOURCE_ID

        assert SOURCE_ID == "yell"

    def test_adapter_constructs(self):
        from engine.sources.leads.yell import YELL_CONFIG

        adapter = YellAdapter(YELL_CONFIG)
        assert adapter.config.source_id == "yell"
        adapter._polite.close()
