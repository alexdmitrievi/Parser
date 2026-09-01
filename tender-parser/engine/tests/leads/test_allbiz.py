"""Тесты адаптера all.biz: разбор JSON-LD и вывод домена из почты."""

from __future__ import annotations

from engine.sources.leads.allbiz import AllBizAdapter


def test_parse_ld_extracts_contacts():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"LocalBusiness","name":"ExportGrain",'
        '"email":"mailto:sales@exportgrain.ru",'
        '"address":{"addressLocality":"Petropavlovsk",'
        '"addressRegion":"Severo-Kazahstanskaja oblast","addressCountry":"Kazakhstan"},'
        '"description":"Wheat supplier"}'
        "</script>"
    )
    info = AllBizAdapter._parse_ld(html)
    assert info["name"] == "ExportGrain"
    assert info["email"] == "sales@exportgrain.ru"
    assert info["country"] == "Kazakhstan"
    assert info["city"] == "Petropavlovsk"
    assert info["region"] == "Severo-Kazahstanskaja oblast"
    assert info["description"] == "Wheat supplier"


def test_parse_ld_skips_malformed_and_absent():
    assert AllBizAdapter._parse_ld("<html>no json</html>") == {}
    assert AllBizAdapter._parse_ld('<script type="application/ld+json">not json</script>') == {}
    # JSON-LD без email не является карточкой продавца
    assert AllBizAdapter._parse_ld(
        '<script type="application/ld+json">{"name":"x"}</script>'
    ) == {}


def test_derive_domain_corporate_and_freemail():
    assert AllBizAdapter._derive_domain("sales@exportgrain.ru") == "exportgrain.ru"
    assert AllBizAdapter._derive_domain("foo@gmail.com") == ""
    assert AllBizAdapter._derive_domain("no-at-sign") == ""
