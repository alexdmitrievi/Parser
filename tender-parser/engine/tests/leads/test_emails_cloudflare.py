"""Тесты приёмов, портированных из Astra Email Extractor.

Покрывают то, чего не было в ``leads.emails`` до интеграции:

* Cloudflare email protection (XOR-декод ``data-cfemail`` и ``email-protection#``);
* русская обфускация (``собака``/``точка`` в символьной и словесной форме).
"""

from __future__ import annotations

import pytest

from leads.emails import deobfuscate, extract_emails


def _cf_encode(email: str, key: int = 0x5F) -> str:
    """Закодировать адрес так, как это делает Cloudflare: первый байт — ключ, остальные — XOR."""
    return f"{key:02x}" + "".join(f"{ord(char) ^ key:02x}" for char in email)


class TestCloudflareProtection:
    def test_decodes_data_cfemail(self):
        email = "info@hongyun-carbon.cn"
        html = f'<a data-cfemail="{_cf_encode(email)}">mail</a>'
        assert email in {e.email for e in extract_emails(html)}

    def test_decodes_email_protection_href(self):
        email = "sales@example.cn"
        html = f'<a href="/cdn-cgi/l/email-protection#{_cf_encode(email, key=0x3A)}">mail</a>'
        assert email in {e.email for e in extract_emails(html)}

    def test_decoded_address_is_lowercased_and_deduped(self):
        email = "Sales@Hongyun-Carbon.CN"
        html = f'<a data-cfemail="{_cf_encode(email)}">a</a>'
        found = [e.email for e in extract_emails(html)]
        assert found == ["sales@hongyun-carbon.cn"]

    def test_decoded_junk_is_still_filtered(self):
        # noreply@ — декодируется, но отсеивается фильтром мусора.
        html = f'<a data-cfemail="{_cf_encode("noreply@example.cn")}">x</a>'
        assert extract_emails(html) == []

    def test_ignores_invalid_hex(self):
        assert extract_emails('<a data-cfemail="zzzz">x</a>') == []
        assert extract_emails('<a data-cfemail="abc">x</a>') == []


class TestRussianObfuscation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("sales (собака) example (точка) cn", "sales@example.cn"),
            ("sales[собака]example[точка]cn", "sales@example.cn"),
            ("sales{собака}example{точка}cn", "sales@example.cn"),
            ("sales собака example точка cn", "sales@example.cn"),
            ("sales (собачка) example (точка) cn", "sales@example.cn"),
        ],
    )
    def test_deobfuscate_expands_russian_forms(self, raw, expected):
        assert deobfuscate(raw) == expected

    @pytest.mark.parametrize(
        "html,expected",
        [
            ("<p>sales[собака]hongyun-carbon[точка]cn</p>", "sales@hongyun-carbon.cn"),
            ("<p>sales собака hongyun-carbon точка cn</p>", "sales@hongyun-carbon.cn"),
            ("<p>export (собака) shandong-coke (точка) com (точка) cn</p>",
             "export@shandong-coke.com.cn"),
        ],
    )
    def test_extracts_russian_obfuscated_addresses(self, html, expected):
        assert expected in {e.email for e in extract_emails(html)}
