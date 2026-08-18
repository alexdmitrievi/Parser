"""Тесты дедупликации, хранилища, экспорта в CSV и списка исключений."""

from __future__ import annotations

import csv

import pytest

from engine.types import CrawlAction
from leads.blacklist import Blacklist
from leads.dedup import LeadsDeduplicator, company_key, dedupe_batch
from leads.export import CSV_COLUMNS, build_rows, export_csv
from leads.models import LeadCompany, LeadEmail
from leads.storage.sqlite_repo import SqliteLeadsRepository


def company(**kwargs) -> LeadCompany:
    defaults = dict(profile="petcoke_anode", source_name="made_in_china")
    defaults.update(kwargs)
    return LeadCompany(**defaults)


@pytest.fixture
def repo(tmp_path) -> SqliteLeadsRepository:
    repository = SqliteLeadsRepository(str(tmp_path / "leads.sqlite3"))
    repository.migrate()
    yield repository
    repository.close()


class TestDedupKey:
    def test_domain_is_the_key_when_present(self):
        assert company_key(company(domain="hongyun-carbon.cn")) == "domain:hongyun-carbon.cn"

    def test_falls_back_to_name_and_province(self):
        key = company_key(company(company_name_en="Kaifeng Anode Ltd", province="Henan"))
        assert key == "name:kaifeng anode|henan"

    def test_legal_form_does_not_split_the_key(self):
        a = company(company_name_en="Shandong Petro-Coke Co., Ltd.", province="Shandong")
        b = company(company_name_en="SHANDONG PETRO COKE INDUSTRIAL CO LTD", province="Shandong")
        assert company_key(a) == company_key(b)

    def test_unidentifiable_record_has_no_key(self):
        assert company_key(company()) == ""


class TestDeduplicator:
    def test_new_company_is_inserted(self):
        assert LeadsDeduplicator().check(company(domain="a.cn"), {}) == CrawlAction.INSERT

    def test_known_company_is_updated(self):
        existing = {"domain:a.cn": company(domain="a.cn")}
        assert LeadsDeduplicator().check(company(domain="a.cn"), existing) == CrawlAction.UPDATE

    def test_unidentifiable_company_is_skipped(self):
        assert LeadsDeduplicator().check(company(), {}) == CrawlAction.SKIP

    def test_merge_fills_missing_fields(self):
        saved = company(domain="a.cn", province="Shandong", city="Zibo",
                        company_name_en="Hongyun Carbon")
        incoming = company(domain="a.cn", source_name="company_site")
        LeadsDeduplicator().merge(incoming, saved)
        assert incoming.province == "Shandong"
        assert incoming.city == "Zibo"
        assert incoming.company_name_en == "Hongyun Carbon"

    def test_merge_unions_emails(self):
        saved = company(domain="a.cn", emails=[LeadEmail(email="sales@a.cn")])
        incoming = company(domain="a.cn", emails=[LeadEmail(email="export@a.cn")])
        LeadsDeduplicator().merge(incoming, saved)
        assert {e.email for e in incoming.emails} == {"sales@a.cn", "export@a.cn"}

    def test_merge_keeps_original_source_url_of_an_email(self):
        saved = company(
            domain="a.cn",
            emails=[LeadEmail(email="sales@a.cn", source_url="https://a.cn/contact")],
        )
        incoming = company(domain="a.cn", emails=[LeadEmail(email="sales@a.cn", source_url="")])
        LeadsDeduplicator().merge(incoming, saved)
        assert incoming.emails[0].source_url == "https://a.cn/contact"

    def test_merge_unions_keywords_and_phones(self):
        saved = company(domain="a.cn", matched_keywords=["CPC"], phones=["+8613800000000"])
        incoming = company(domain="a.cn", matched_keywords=["anode grade coke"])
        LeadsDeduplicator().merge(incoming, saved)
        assert set(incoming.matched_keywords) == {"CPC", "anode grade coke"}
        assert incoming.phones == ["+8613800000000"]

    def test_merge_does_not_reset_enrich_status(self):
        saved = company(domain="a.cn", enrich_status="done")
        incoming = company(domain="a.cn", enrich_status="pending")
        LeadsDeduplicator().merge(incoming, saved)
        assert incoming.enrich_status == "done"

    def test_higher_priority_source_wins_on_conflict(self):
        saved = company(domain="a.cn", province="Shandong", source_name="customs_api")
        incoming = company(domain="a.cn", province="Hebei", source_name="made_in_china")
        LeadsDeduplicator().merge(incoming, saved)
        assert incoming.province == "Shandong"

    def test_dedupe_batch_collapses_duplicates(self):
        batch = [
            company(domain="a.cn", emails=[LeadEmail(email="sales@a.cn")]),
            company(domain="a.cn", emails=[LeadEmail(email="export@a.cn")]),
            company(domain="b.cn"),
        ]
        merged = dedupe_batch(batch)
        assert len(merged) == 2
        by_domain = {c.domain: c for c in merged}
        assert len(by_domain["a.cn"].emails) == 2


class TestStorage:
    def test_migration_is_idempotent(self, repo):
        repo.migrate()
        repo.migrate()
        assert repo.iter_companies() == []

    def test_repeated_collect_creates_no_duplicates(self, repo):
        batch = [company(domain="a.cn", company_name_en="A Ltd")]
        assert repo.upsert_companies(batch) == (1, 0)
        assert repo.upsert_companies(batch) == (0, 1)
        assert len(repo.iter_companies()) == 1

    def test_emails_round_trip_with_source_url(self, repo):
        repo.upsert_companies([
            company(
                domain="a.cn",
                emails=[LeadEmail(email="sales@a.cn", kind="role", source_url="https://a.cn/c")],
            )
        ])
        saved = repo.iter_companies()[0]
        assert saved.emails[0].email == "sales@a.cn"
        assert saved.emails[0].source_url == "https://a.cn/c"

    def test_re_enrichment_does_not_duplicate_emails(self, repo):
        record = company(domain="a.cn", emails=[LeadEmail(email="sales@a.cn")])
        repo.upsert_companies([record])
        repo.upsert_companies([record])
        assert len(repo.iter_companies()[0].emails) == 1

    def test_filters_by_status_and_domain(self, repo):
        repo.upsert_companies([
            company(domain="a.cn", enrich_status="pending"),
            company(domain="b.cn", enrich_status="done"),
            company(company_name_en="No Site Ltd", province="Henan", enrich_status="no_site"),
        ])
        pending = repo.iter_companies(enrich_status="pending", with_domain_only=True)
        assert [c.domain for c in pending] == ["a.cn"]

    def test_stats_counts_role_and_personal(self, repo):
        repo.upsert_companies([
            company(domain="a.cn", province="Shandong", emails=[
                LeadEmail(email="sales@a.cn", kind="role"),
                LeadEmail(email="li.wei@a.cn", kind="personal"),
            ]),
            company(domain="b.cn", province="Hebei"),
        ])
        stats = repo.stats()
        assert stats["companies"] == 2
        assert stats["companies_with_emails"] == 1
        assert (stats["emails"], stats["emails_role"], stats["emails_personal"]) == (2, 1, 1)
        assert stats["by_province"]["Shandong"] == 1


class TestBlacklist:
    def test_blocks_listed_domain_and_subdomains(self):
        blacklist = Blacklist(domains={"example.com"})
        assert blacklist.blocks_domain("example.com") is True
        assert blacklist.blocks_domain("shop.example.com") is True
        assert blacklist.blocks_domain("notexample.com") is False

    def test_blocks_specific_address(self):
        blacklist = Blacklist(emails={"opt-out@a.cn"})
        assert blacklist.blocks_email("opt-out@a.cn") is True
        assert blacklist.blocks_email("sales@a.cn") is False

    def test_domain_entry_blocks_all_its_addresses(self):
        assert Blacklist(domains={"a.cn"}).blocks_email("sales@a.cn") is True

    def test_loads_file_ignoring_comments(self, tmp_path):
        path = tmp_path / "bl.txt"
        path.write_text(
            "# комментарий\n\nexample.com\nopt-out@a.cn  # отписался\n", encoding="utf-8"
        )
        blacklist = Blacklist.load(path)
        assert blacklist.blocks_domain("example.com") is True
        assert blacklist.blocks_email("opt-out@a.cn") is True

    def test_missing_file_is_an_empty_list(self, tmp_path):
        assert len(Blacklist.load(tmp_path / "nope.txt")) == 0


class TestExport:
    def _company_with_emails(self) -> LeadCompany:
        return company(
            company_name_en="Hongyun Carbon Co., Ltd.",
            domain="hongyun-carbon.cn",
            website="https://hongyun-carbon.cn",
            province="Shandong",
            city="Zibo",
            emails=[
                LeadEmail(email="sales@hongyun-carbon.cn", kind="role"),
                LeadEmail(email="li.wei@hongyun-carbon.cn", kind="personal"),
            ],
        )

    def test_one_row_per_email(self):
        rows, _ = build_rows([self._company_with_emails()], include_personal=True)
        assert len(rows) == 2

    def test_personal_addresses_are_excluded_by_default(self):
        """PIPL: именные адреса не выгружаются без явного флага."""
        rows, result = build_rows([self._company_with_emails()])
        assert [r["Email"] for r in rows] == ["sales@hongyun-carbon.cn"]
        assert result.skipped_personal == 1

    def test_include_personal_flag_adds_them(self):
        rows, _ = build_rows([self._company_with_emails()], include_personal=True)
        assert "li.wei@hongyun-carbon.cn" in {r["Email"] for r in rows}

    def test_blacklisted_domain_is_never_exported(self):
        rows, result = build_rows(
            [self._company_with_emails()], blacklist=Blacklist(domains={"hongyun-carbon.cn"})
        )
        assert rows == []
        assert result.skipped_blacklist == 2

    def test_blacklisted_address_is_dropped(self):
        rows, _ = build_rows(
            [self._company_with_emails()],
            blacklist=Blacklist(emails={"sales@hongyun-carbon.cn"}),
        )
        assert rows == []

    def test_company_without_emails_is_skipped(self):
        rows, result = build_rows([company(domain="a.cn")])
        assert rows == []
        assert result.skipped_no_email == 1

    def test_priority_provinces_come_first(self, profile_config):
        hebei = company(domain="b.cn", company_name_en="B", province="Hebei",
                        emails=[LeadEmail(email="sales@b.cn")])
        shandong = company(domain="a.cn", company_name_en="A", province="Shandong",
                           emails=[LeadEmail(email="sales@a.cn")])
        elsewhere = company(domain="c.cn", company_name_en="C", province="Yunnan",
                            emails=[LeadEmail(email="sales@c.cn")])
        rows, _ = build_rows([elsewhere, hebei, shandong], profiles=profile_config)
        assert [r["Province"] for r in rows] == ["Shandong", "Hebei", "Yunnan"]

    def test_csv_has_exact_coldy_columns(self, tmp_path):
        out = tmp_path / "leads.csv"
        export_csv([self._company_with_emails()], out)
        with out.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            assert tuple(reader.fieldnames or ()) == CSV_COLUMNS

    def test_csv_written_even_when_empty(self, tmp_path):
        out = tmp_path / "empty.csv"
        result = export_csv([], out)
        assert out.exists() and result.rows == 0
        assert out.read_text(encoding="utf-8-sig").strip() == ",".join(CSV_COLUMNS)

    def test_csv_survives_chinese_names(self, tmp_path):
        out = tmp_path / "zh.csv"
        export_csv([company(
            company_name_zh="山东宏运碳素",
            domain="a.cn",
            emails=[LeadEmail(email="sales@a.cn")],
        )], out)
        with out.open(encoding="utf-8-sig", newline="") as handle:
            assert next(csv.DictReader(handle))["Company"] == "山东宏运碳素"
