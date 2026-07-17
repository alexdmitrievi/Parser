"""Tests for the EIS FTP source: XML parsing, region matching, adapter flow."""

import os
import sys
import zipfile


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.sources.tenders.eis_ftp import (
    DEFAULT_REGIONS,
    EIS_FTP_44_CONFIG,
    LAYOUT_44,
    EisFtpSourceAdapter,
    EisRegion,
    _region_match,
    parse_44fz_notification,
    parse_223fz_notice,
)
from engine.normalizers.tender_normalizer import TenderNormalizer
from engine.types import FetchResult, ParsedRecord
from engine.tests.fixtures import (
    NOTIFICATION_44FZ_EF,
    NOTIFICATION_44FZ_STOPWORD,
    NOTICE_223FZ,
)


class TestParse44fz:
    def test_full_notification(self):
        rec = parse_44fz_notification(NOTIFICATION_44FZ_EF)
        assert rec is not None
        assert rec["registry_number"] == "0152300011926000042"
        assert "расчистке территории" in rec["title"]
        assert rec["customer_name"].startswith("АДМИНИСТРАЦИЯ СОВЕТСКОГО")
        assert rec["customer_inn"] == "5501021880"
        assert rec["nmck"] == 1250000.0
        assert rec["application_guarantee"] == 12500.0
        assert rec["contract_guarantee"] == 62500.0
        assert rec["purchase_method"] == "Электронный аукцион"
        assert rec["law_type"] == "44-fz"
        assert rec["submission_deadline"] is not None
        assert rec["submission_deadline"].day == 22
        assert rec["publish_date"] is not None
        assert "81.30.10.131" in rec["okpd2_codes"]
        assert "43.12.11.100" in rec["okpd2_codes"]
        assert rec["original_url"].startswith("https://zakupki.gov.ru/epz/order/notice")
        assert "regNumber=0152300011926000042" in rec["original_url"]

    def test_no_purchase_number_returns_none(self):
        assert parse_44fz_notification("<export><doc><foo>1</foo></doc></export>") is None

    def test_invalid_xml_returns_none(self):
        assert parse_44fz_notification("не xml вообще") is None

    def test_url_fallback_without_href(self):
        xml = NOTIFICATION_44FZ_EF.replace(
            "<href>https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0152300011926000042</href>",
            "",
        )
        rec = parse_44fz_notification(xml)
        assert rec is not None
        # Без href — универсальная ссылка на поиск по номеру (путь карточки
        # зависит от способа закупки и не угадывается)
        assert "searchString=0152300011926000042" in rec["original_url"]


class TestParse223fz:
    def test_full_notice(self):
        rec = parse_223fz_notice(NOTICE_223FZ)
        assert rec is not None
        assert rec["registry_number"] == "32615544332"
        assert "печного топлива" in rec["title"]
        assert "СИБИРСКИЕ КОММУНАЛЬНЫЕ" in rec["customer_name"]
        assert rec["customer_inn"] == "5406012345"
        assert rec["nmck"] == 4800000.0
        assert rec["purchase_method"] == "Запрос котировок в электронной форме"
        assert rec["law_type"] == "223-fz"
        assert rec["submission_deadline"].day == 21
        assert "19.20.28.120" in rec["okpd2_codes"]
        assert "regNumber=32615544332" in rec["original_url"]

    def test_invalid_returns_none(self):
        assert parse_223fz_notice("<purchaseNotice/>") is None


class TestNaiveDatetime:
    def test_naive_datetime_assumed_msk(self):
        # Регрессия: naive-дата без смещения ложилась в TIMESTAMPTZ как UTC
        # и дедлайн в карточке уезжал на 3 часа
        from engine.sources.tenders.eis_ftp import _to_dt
        dt = _to_dt("2026-07-22T08:00:00")
        assert dt is not None and dt.tzinfo is not None
        assert dt.utcoffset().total_seconds() == 3 * 3600

    def test_explicit_offset_preserved(self):
        from engine.sources.tenders.eis_ftp import _to_dt
        dt = _to_dt("2026-07-22T08:00:00+05:00")
        assert dt.utcoffset().total_seconds() == 5 * 3600


class TestRegionMatch:
    def test_transliteration_variants(self):
        omsk = EisRegion(match="omsk", display_name="Омская область")
        assert _region_match(["Omskaja_obl", "Tomskaja_obl"], omsk) == "Omskaja_obl"
        assert _region_match(["Omskaya_obl"], omsk) == "Omskaya_obl"
        assert _region_match(["/fcs_regions/Omskaja_obl"], omsk) == "Omskaja_obl"

    def test_tomsk_is_not_omsk(self):
        # Регрессия: подстрочный матч находил "omsk" внутри "Tomskaja_obl"
        omsk = EisRegion(match="omsk", display_name="Омская область")
        assert _region_match(["Tomskaja_obl"], omsk) is None
        assert _region_match(["Tomskaja_obl", "Omskaja_obl"], omsk) == "Omskaja_obl"
        assert _region_match(["Томская_обл"], omsk) is None

    def test_russian_dir_names(self):
        omsk = EisRegion(match="omsk", display_name="Омская область")
        assert _region_match(["Омская_обл", "Томская_обл"], omsk) == "Омская_обл"

    def test_not_found(self):
        novosib = EisRegion(match="novosibirsk", display_name="Новосибирская область")
        assert _region_match(["Omskaja_obl"], novosib) is None

    def test_default_regions(self):
        assert [r.display_name for r in DEFAULT_REGIONS] == [
            "Омская область", "Новосибирская область",
        ]


class _FakeRepo:
    def __init__(self, processed=None):
        self.processed = set(processed or [])
        self.marked: list[str] = []

    def filter_new_archives(self, paths):
        return [p for p in paths if p not in self.processed]

    def mark_archives_processed(self, paths, source_id):
        self.marked.extend(paths)
        self.processed.update(paths)


def _make_zip(tmp_path, name, xml_map):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for inner, content in xml_map.items():
            zf.writestr(inner, content)
    return str(path)


class TestAdapter:
    def _adapter(self, repo=None):
        return EisFtpSourceAdapter(EIS_FTP_44_CONFIG, LAYOUT_44, repo=repo)

    def test_parse_listing_from_zip(self, tmp_path):
        zip_path = _make_zip(tmp_path, "notification_test.xml.zip", {
            "fcsNotificationEF_1.xml": NOTIFICATION_44FZ_EF,
            "fcsNotificationCancel_2.xml": NOTIFICATION_44FZ_EF,  # пропускается по имени
            "readme.txt": "not xml",
        })
        adapter = self._adapter()
        url = "/fcs_regions/Omskaja_obl/notifications/currMonth/notification_test.xml.zip"
        adapter._region_by_path[url] = "Омская область"

        result = FetchResult(url=url, content=zip_path, content_type="application/zip+local-path")
        records = adapter.parse_listing(result)

        assert len(records) == 1
        rec = records[0]
        assert isinstance(rec, ParsedRecord)
        assert rec.registry_number == "0152300011926000042"
        assert rec.customer_region == "Омская область"
        assert rec.application_guarantee == 12500.0
        # архив удалён с диска после разбора
        assert not os.path.exists(zip_path)
        # архив попал в очередь на пометку «обработан»
        assert adapter.parsed_archives == [url]

    def test_bad_zip_does_not_crash(self, tmp_path):
        bad = tmp_path / "bad.xml.zip"
        bad.write_bytes(b"garbage")
        adapter = self._adapter()
        result = FetchResult(url="x.zip", content=str(bad), content_type="application/zip+local-path")
        assert adapter.parse_listing(result) == []
        assert not os.path.exists(bad)

    def test_commit_processed_marks_repo(self, tmp_path):
        repo = _FakeRepo()
        adapter = self._adapter(repo=repo)
        adapter.parsed_archives = ["a.zip", "b.zip"]
        adapter.commit_processed()
        assert repo.marked == ["a.zip", "b.zip"]
        assert adapter.parsed_archives == []

    def test_orchestrator_flags(self):
        adapter = self._adapter()
        assert adapter.stop_on_empty_page is False
        assert adapter.empty_discovery_ok is True
        assert adapter.empty_parse_ok is True


class TestNormalizerIntegration:
    def test_guarantees_survive_normalization(self):
        fields = parse_44fz_notification(NOTIFICATION_44FZ_EF)
        record = ParsedRecord(source_id="eis_ftp_44", customer_region="Омская область", **fields)
        normalized = TenderNormalizer().normalize(record)
        assert normalized is not None
        assert normalized["application_guarantee"] == 12500.0
        assert normalized["contract_guarantee"] == 62500.0
        assert normalized["customer_region"] == "Омская область"
        assert normalized["law_type"] == "44-fz"

    def test_stopword_notification_parses(self):
        # Стоп-слова отфильтровываются на этапе уведомлений, не парсинга
        rec = parse_44fz_notification(NOTIFICATION_44FZ_STOPWORD)
        assert rec is not None
        assert "многоквартирных" in rec["title"]
