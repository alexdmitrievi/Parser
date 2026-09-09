"""Тесты разбора карточек каталога и определения географии."""

from __future__ import annotations

import pytest

from engine.fetchers.polite_fetcher import PoliteResponse
from engine.sources.leads.made_in_china import MADE_IN_CHINA_CONFIG, MadeInChinaAdapter
from leads.normalizer import (
    company_name_key,
    detect_city,
    detect_province,
    is_company_domain,
    normalize_domain,
    normalize_website,
    split_name_by_script,
)


@pytest.fixture
def adapter(petcoke_profile, profile_config) -> MadeInChinaAdapter:
    """Адаптер без сети: фетчер не создаётся, пока не вызван fetch_page."""
    return MadeInChinaAdapter(
        MADE_IN_CHINA_CONFIG,
        profile=petcoke_profile,
        limits=profile_config.limits,
        user_agent="TestBot/1.0 (+mailto:test@example.com)",
    )


def _response(html: str) -> PoliteResponse:
    return PoliteResponse(
        url="https://www.made-in-china.com/products-search/hot-china-products/calcined_petroleum_coke.html",
        status_code=200,
        text=html,
    )


class TestCardParsing:
    def test_parses_all_named_cards(self, adapter, catalog_html):
        companies = adapter.parse_companies(_response(catalog_html))
        assert len(companies) == 2  # карточка без названия пропущена

    def test_splits_latin_and_chinese_names(self, adapter, catalog_html):
        first = adapter.parse_companies(_response(catalog_html))[0]
        assert first.company_name_en == "Shandong Hongyun Carbon Co., Ltd."
        assert first.company_name_zh == ""

    def test_extracts_province_and_city(self, adapter, catalog_html):
        companies = adapter.parse_companies(_response(catalog_html))
        assert (companies[0].province, companies[0].city) == ("Shandong", "Zibo")
        assert companies[1].province == "Zhejiang"

    def test_catalog_does_not_expose_website(self, adapter, catalog_html):
        """Витрина made-in-china сайтом компании не считается — домен пустой."""
        companies = adapter.parse_companies(_response(catalog_html))
        assert all(c.domain == "" for c in companies)
        assert all(c.enrich_status == "no_site" for c in companies)

    def test_records_matched_keywords_and_industry(self, adapter, catalog_html):
        first = adapter.parse_companies(_response(catalog_html))[0]
        assert "calcined petroleum coke" in first.matched_keywords
        assert first.industry_guess == "aluminium"

    def test_records_source(self, adapter, catalog_html):
        first = adapter.parse_companies(_response(catalog_html))[0]
        assert first.source_name == "made_in_china"
        assert first.source_url.endswith("/calcined_petroleum_coke.html")
        assert first.profile == "petcoke_anode"
        assert first.country == "China"

    def test_empty_page_yields_nothing(self, adapter):
        assert adapter.parse_companies(_response("<html><body></body></html>")) == []

    def test_selectors_are_configurable(self, petcoke_profile, profile_config):
        """Смена вёрстки чинится конфигом, а не правкой кода."""
        config = MADE_IN_CHINA_CONFIG
        custom = type(config)(
            source_id=config.source_id,
            platform_name=config.platform_name,
            category=config.category,
            base_url=config.base_url,
            selectors={"list_item": ".row", "company_name": ".n a"},
        )
        adapter = MadeInChinaAdapter(
            custom, profile=petcoke_profile, limits=profile_config.limits, user_agent="T/1.0"
        )
        html = '<div class="row"><div class="n"><a href="https://x.en.made-in-china.com">New Layout Co Ltd</a></div><div>Jiangsu, China</div></div>'
        assert adapter.parse_companies(_response(html))[0].company_name_en == "New Layout Co Ltd"


class TestDiscovery:
    def test_builds_one_url_per_english_keyword(self, adapter):
        urls = adapter.discover()
        # только английские ключи (slug латинский), по одному URL на ключ
        assert len(urls) == len(adapter.profile.keywords_en)
        assert all("made-in-china.com" in u for u in urls)
        assert all("/products-search/hot-china-products/" in u for u in urls)
        assert any("calcined_petroleum_coke" in u for u in urls)

    def test_no_pagination_in_urls(self, adapter):
        assert not any("page=" in u for u in adapter.discover())


class TestGeography:
    @pytest.mark.parametrize(
        "text,province",
        [
            ("No. 5 Road, Zibo, Shandong, China", "Shandong"),
            ("山东省淄博市", "Shandong"),
            ("Kaifeng, Henan", "Henan"),
            ("陕西省西安市", "Shaanxi"),
            ("山西太原", "Shanxi"),
            ("Urumqi factory", "Xinjiang"),
            ("Inner Mongolia Baotou", "Inner Mongolia"),
            ("нет географии", ""),
        ],
    )
    def test_detect_province(self, text, province):
        assert detect_province(text) == province

    def test_detect_city(self):
        assert detect_city("Qingdao Port area") == "Qingdao"
        assert detect_city("no city") == ""


class TestNormalizer:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("https://WWW.Example.COM:443/contact?x=1", "example.com"),
            ("http://example.com/", "example.com"),
            ("example.com", "example.com"),
            ("sales@Foo.Bar.CN", "foo.bar.cn"),
            ("", ""),
            ("not a domain", ""),
        ],
    )
    def test_normalize_domain(self, raw, expected):
        assert normalize_domain(raw) == expected

    def test_normalize_website(self):
        assert normalize_website("http://www.example.com/x") == "https://example.com"

    @pytest.mark.parametrize(
        "domain,is_company",
        [
            ("hongyun-carbon.cn", True),
            ("made-in-china.com", False),
            ("hongyun.en.made-in-china.com", False),
            ("alibaba.com", False),
            ("163.com", False),
        ],
    )
    def test_is_company_domain(self, domain, is_company):
        assert is_company_domain(domain) is is_company

    def test_name_key_ignores_legal_form_and_punctuation(self):
        assert company_name_key("Shandong Petro-Coke Co., Ltd.") == company_name_key(
            "SHANDONG PETRO COKE INDUSTRIAL CO LTD"
        )

    def test_split_name_by_script(self):
        assert split_name_by_script("山东宏运 Shandong Hongyun Co., Ltd") == (
            "Shandong Hongyun Co., Ltd",
            "山东宏运",
        )
        assert split_name_by_script("Pure Latin Ltd") == ("Pure Latin Ltd", "")
        assert split_name_by_script("山东宏运") == ("", "山东宏运")
