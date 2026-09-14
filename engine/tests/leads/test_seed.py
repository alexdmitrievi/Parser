"""Тесты разбора файлов-сидов (домены, CSV, Excel)."""

from __future__ import annotations

import pytest

from leads.seed import parse_seed_file


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_txt_domains(tmp_path):
    path = _write(tmp_path, "domains.txt", "example.com\n# comment\nfoo.cn\n\nbar.kz\n")
    records = parse_seed_file(path)
    assert [r.website for r in records] == ["example.com", "foo.cn", "bar.kz"]


def test_csv_with_columns(tmp_path):
    path = _write(
        tmp_path,
        "companies.csv",
        "name,website,country,hs_code\n"
        "Shandong Agri,shandong-agri.cn,CN,8432\n"
        "Astana Agro,astana-agro.kz,KZ,1001\n",
    )
    records = parse_seed_file(path)
    assert len(records) == 2
    assert records[0].name == "Shandong Agri"
    assert records[0].website == "shandong-agri.cn"
    assert records[0].country == "CN"
    assert records[0].hs_code == "8432"
    assert records[1].country == "KZ"


def test_csv_domain_alias(tmp_path):
    path = _write(tmp_path, "companies.csv", "company,domain\nFoo Ltd,foo.com\n")
    records = parse_seed_file(path)
    assert records[0].name == "Foo Ltd"
    assert records[0].website == "foo.com"


def test_csv_skips_rows_without_website(tmp_path):
    path = _write(tmp_path, "companies.csv", "name,website\nNoSite,\nHasSite,has.com\n")
    records = parse_seed_file(path)
    assert [r.website for r in records] == ["has.com"]


def test_unsupported_extension(tmp_path):
    path = _write(tmp_path, "companies.json", "{}")
    with pytest.raises(ValueError):
        parse_seed_file(path)


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_seed_file(tmp_path / "nope.csv")


def test_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "website", "country", "hs_code"])
    ws.append(["Anadolu Gida", "anadolu-gida.com.tr", "TR", "1001"])
    path = tmp_path / "companies.xlsx"
    wb.save(path)
    records = parse_seed_file(path)
    assert records[0].name == "Anadolu Gida"
    assert records[0].country == "TR"


def test_companies_from_seed(tmp_path):
    from leads.pipeline import LeadsPipeline
    from leads.profiles import Limits, Profile, ProfileConfig
    from leads.seed import SeedRecord
    from leads.storage.sqlite_repo import SqliteLeadsRepository

    profile = Profile(name="grain", keywords_en=["wheat"], hs_codes=["1001"])
    profiles = ProfileConfig(
        profiles={"grain": profile},
        limits=Limits(max_pages_per_query=2, request_delay_seconds=0.0, max_concurrency=1),
    )
    repo = SqliteLeadsRepository(str(tmp_path / "leads.sqlite3"))
    repo.migrate()
    pipeline = LeadsPipeline(repo, profiles)

    records = [
        SeedRecord(website="shandong-agri.cn", name="Shandong Agri Machinery", country="CN", hs_code="8432"),
        SeedRecord(website="astana-agro.kz", name="Astana Agro", country="KZ", hs_code="1001"),
    ]
    companies = pipeline._companies_from_seed(records, profile)
    repo.close()

    assert len(companies) == 2
    assert companies[0].domain == "shandong-agri.cn"
    assert companies[0].country == "CN"
    assert companies[0].matched_keywords == ["8432"]
    assert companies[0].source_name == "seed_file"
    assert companies[1].country == "KZ"
    assert companies[1].company_name_en == "Astana Agro"
