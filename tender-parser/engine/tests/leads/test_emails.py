"""Тесты извлечения, деобфускации, фильтрации и классификации почт."""

from __future__ import annotations

import pytest

from leads.emails import (
    classify,
    deobfuscate,
    emails_for_domain,
    extract_emails,
    is_junk,
    normalize_email,
)
from leads.models import EMAIL_KIND_PERSONAL, EMAIL_KIND_ROLE


class TestExtraction:
    def test_extracts_from_mailto(self):
        found = extract_emails('<a href="mailto:sales@example.cn">write</a>')
        assert [e.email for e in found] == ["sales@example.cn"]

    def test_extracts_from_plain_text(self):
        found = extract_emails("<p>Contact: info@hongyun-carbon.cn today</p>")
        assert [e.email for e in found] == ["info@hongyun-carbon.cn"]

    def test_lowercases_addresses(self):
        found = extract_emails('<a href="mailto:Sales@Hongyun-Carbon.CN">x</a>')
        assert found[0].email == "sales@hongyun-carbon.cn"

    def test_records_source_url_for_each_address(self):
        url = "https://hongyun-carbon.cn/contact"
        found = extract_emails("<p>info@hongyun-carbon.cn</p>", source_url=url)
        assert all(e.source_url == url for e in found)

    def test_deduplicates_by_domain_and_local_part(self):
        html = """
          <a href="mailto:Info@hongyun-carbon.cn">a</a>
          <p>info@hongyun-carbon.cn</p>
          <p>INFO@HONGYUN-CARBON.CN</p>
        """
        assert len(extract_emails(html)) == 1

    def test_empty_input_returns_empty(self):
        assert extract_emails("") == []

    def test_finds_every_form_on_a_real_contact_page(self, contact_html):
        found = {e.email for e in extract_emails(contact_html)}
        assert {
            "sales@hongyun-carbon.cn",
            "export@hongyun-carbon.cn",
            "trade@hongyun-carbon.cn",
            "li.wei@hongyun-carbon.cn",
            "zhangwei@hongyun-carbon.cn",
            "info@hongyun-carbon.cn",
        } <= found


class TestDeobfuscation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("sales (at) example (dot) cn", "sales@example.cn"),
            ("sales[at]example[dot]cn", "sales@example.cn"),
            ("sales{at}example{dot}cn", "sales@example.cn"),
            ("sales AT example DOT cn", "sales@example.cn"),
        ],
    )
    def test_deobfuscate_expands_known_forms(self, raw, expected):
        assert deobfuscate(raw) == expected

    @pytest.mark.parametrize(
        "html,expected",
        [
            ("<p>sales (at) hongyun-carbon (dot) cn</p>", "sales@hongyun-carbon.cn"),
            ("<p>sales[at]hongyun-carbon[dot]cn</p>", "sales@hongyun-carbon.cn"),
            ("<p>sales#hongyun-carbon.cn</p>", "sales@hongyun-carbon.cn"),
            ("<p>sales&#64;hongyun-carbon&#46;cn</p>", "sales@hongyun-carbon.cn"),
            ("<p>sales AT hongyun-carbon DOT cn</p>", "sales@hongyun-carbon.cn"),
        ],
    )
    def test_extracts_obfuscated_addresses(self, html, expected):
        assert expected in {e.email for e in extract_emails(html)}

    def test_bare_at_with_plain_dot_is_not_an_address(self):
        """'look at google.com' — не почта.

        Словесный 'at' принимается только в паре со словесным 'dot'.
        """
        found = {e.email for e in extract_emails("<p>Please look at google.com now</p>")}
        assert "look@google.com" not in found

    def test_url_fragment_is_not_an_address(self):
        found = {e.email for e in extract_emails('<a href="/page#top.html">top</a>')}
        assert found == set()


class TestJunkFiltering:
    @pytest.mark.parametrize(
        "email",
        [
            "noreply@hongyun-carbon.cn",
            "no-reply@hongyun-carbon.cn",
            "donotreply@hongyun-carbon.cn",
            "postmaster@hongyun-carbon.cn",
            "test@example.com",
            "info@example.com",
            "someone@sentry.io",
            "abc@o123.ingest.sentry.io",
            "user@wixpress.com",
            "name@yourdomain.com",
            "logo@2x.png",
            "icon@3x.jpg",
        ],
    )
    def test_junk_addresses_are_rejected(self, email):
        assert is_junk(email) is True

    @pytest.mark.parametrize(
        "email",
        ["sales@hongyun-carbon.cn", "export@shandong-coke.com.cn", "li.wei@kaifeng-anode.cn"],
    )
    def test_real_addresses_are_kept(self, email):
        assert is_junk(email) is False

    def test_junk_is_filtered_out_of_extraction(self, contact_html):
        found = {e.email for e in extract_emails(contact_html)}
        assert "noreply@hongyun-carbon.cn" not in found
        assert "webmaster@example.com" not in found
        assert "someone@sentry.io" not in found
        assert not any(e.endswith(".png") for e in found)


class TestClassification:
    @pytest.mark.parametrize(
        "email",
        [
            "info@x.cn", "sales@x.cn", "export@x.cn", "trade@x.cn",
            "purchase@x.cn", "office@x.cn", "inquiry@x.cn",
            "sales2@x.cn", "export01@x.cn",
            "sales-cn@x.cn", "info.hk@x.cn", "export_2@x.cn",
        ],
    )
    def test_role_addresses(self, email):
        assert classify(email) == EMAIL_KIND_ROLE

    @pytest.mark.parametrize(
        "email", ["li.wei@x.cn", "zhangwei@x.cn", "j.smith@x.cn", "wanglei2020@x.cn"]
    )
    def test_personal_addresses(self, email):
        assert classify(email) == EMAIL_KIND_PERSONAL

    def test_extraction_sets_kind(self, contact_html):
        by_email = {e.email: e.kind for e in extract_emails(contact_html)}
        assert by_email["sales@hongyun-carbon.cn"] == EMAIL_KIND_ROLE
        assert by_email["li.wei@hongyun-carbon.cn"] == EMAIL_KIND_PERSONAL


class TestNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("  Sales@Example.CN  ", "sales@example.cn"),
            ("<sales@example.cn>", "sales@example.cn"),
            ("sales@example.cn?subject=Hi", "sales@example.cn"),
            ("sales%40example.cn", "sales@example.cn"),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert normalize_email(raw) == expected

    @pytest.mark.parametrize("raw", ["", "not-an-email", "a@b", "a@@b.cn", "@example.cn"])
    def test_rejects_invalid(self, raw):
        assert normalize_email(raw) == ""


class TestDomainScoping:
    def test_keeps_only_company_domain(self, contact_html):
        found = extract_emails(contact_html)
        kept = {e.email for e in emails_for_domain(found, "hongyun-carbon.cn")}
        assert "sales@hongyun-carbon.cn" in kept
        # Почта студии-подрядчика компании не принадлежит.
        assert "studio@webdesign-agency.com" not in kept

    def test_subdomain_counts_as_company(self):
        found = extract_emails("<p>sales@mail.hongyun-carbon.cn</p>")
        assert emails_for_domain(found, "hongyun-carbon.cn")

    def test_no_domain_keeps_everything(self):
        found = extract_emails("<p>a@b.cn</p><p>c@d.com</p>")
        assert len(emails_for_domain(found, "")) == 2
