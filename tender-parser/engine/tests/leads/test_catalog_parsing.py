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
        url="https://www.made-in-china.com/productdirectory.do?word=cpc&page=1",
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
        assert first.company_name_zh == "山东宏运"

    def test_extracts_province_and_city(self, adapter, catalog_html):
        companies = adapter.parse_companies(_response(catalog_html))
        assert (companies[0].province, companies[0].city) == ("Shandong", "Zibo")
        assert companies[1].province == "Henan"

    def test_extracts_company_website(self, adapter, catalog_html):
        first = adapter.parse_companies(_response(catalog_html))[0]
        assert first.domain == "hongyun-carbon.cn"
        assert first.website == "https://hongyun-carbon.cn"

    def test_records_matched_keywords_and_industry(self, adapter, catalog_html):
        first = adapter.parse_companies(_response(catalog_html))[0]
        assert "calcined petroleum coke" in first.matched_keywords
        assert first.industry_guess == "aluminium"

    def test_records_source(self, adapter, catalog_html):
        first = adapter.parse_companies(_response(catalog_html))[0]
        assert first.source_name == "made_in_china"
        assert first.source_url.endswith("/company/hongyun.html")
        assert first.profile == "petcoke_anode"

    def test_card_without_website_is_marked_no_site(self, adapter, catalog_html):
        second = adapter.parse_companies(_response(catalog_html))[1]
        assert second.domain == ""
        assert second.enrich_status == "no_site"

    def test_catalog_showcase_is_not_a_company_website(self, adapter):
        """Ссылка на витрину внутри каталога сайтом компании не считается."""
        html = """
        <div class="prod-list"><div class="item">
          <div class="company-name">
            <a href="https://hongyun.en.made-in-china.com/">Hongyun Carbon</a>
          </div>
          <div class="company-location">Zibo, Shandong</div>
        </div></div>
        """
        company = adapter.parse_companies(_response(html))[0]
        assert company.domain == ""

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
            selectors={"list_item": ".row", "company_name": ".n a", "company_link": ".n a"},
        )
        adapter = MadeInChinaAdapter(
            custom, profile=petcoke_profile, limits=profile_config.limits, user_agent="T/1.0"
        )
        html = '<div class="row"><div class="n"><a href="/c/1">New Layout Co Ltd</a></div></div>'
        assert adapter.parse_companies(_response(html))[0].company_name_en == "New Layout Co Ltd"


class TestDiscovery:
    def test_builds_urls_for_keywords_and_pages(self, adapter):
        urls = adapter.discover()
        # 4 английских + 2 китайских ключа × 2 страницы (max_pages_per_query=2)
        assert len(urls) == len(adapter.profile.all_keywords) * 2
        assert all("made-in-china.com" in u for u in urls)
        assert any("page=2" in u for u in urls)

    def test_respects_profile_page_limit(self, adapter):
        assert not any("page=3" in u for u in adapter.discover())


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
