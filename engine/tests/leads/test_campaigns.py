"""Тесты слоя кампаний лидогенерации (leads.campaigns).

Кампания = ниша + гео + язык + направление: самодостаточный конфиг под запрос
конкретного заказчика. Проверяется загрузка YAML, валидация и генерация
Profile + целей 2ГИС из кампании.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from leads.campaigns import (
    CampaignError,
    load_campaigns,
)
from leads.gis2 import Gis2Target


CAMPAIGN_YAML = textwrap.dedent("""\
    campaigns:
      omsk_machines:
        niche_name: "Промышленное оборудование"
        keywords_en: ["machine tool", "cnc machine"]
        keywords_ru: ["станки", "промышленное оборудование"]
        hs_codes: ["8456"]
        target_industries: ["machine tools", "metalworking"]
        direction: import
        language: ru
        countries: ["Russia"]
        gis2:
          domain: ru
          cities: ["omsk", "novosibirsk"]
          rubrics:
            - {code: "614", name: "Металлообрабатывающее оборудование"}
            - {code: "112", name: "Промышленное оборудование"}
      cn_export_grain:
        niche_name: "Зерно (экспорт в КНР)"
        keywords_en: ["wheat", "barley"]
        keywords_ru: []
        hs_codes: ["1001"]
        target_industries: ["flour milling"]
        direction: export
        language: en
        countries: ["China"]
        gis2: {}
    limits:
      request_delay_seconds: 3
      max_concurrency: 2
""")


@pytest.fixture()
def campaigns_file(tmp_path: Path) -> Path:
    path = tmp_path / "lead_campaigns.yaml"
    path.write_text(CAMPAIGN_YAML, encoding="utf-8")
    return path


class TestLoadCampaigns:
    def test_load_all(self, campaigns_file: Path):
        config = load_campaigns(campaigns_file)
        assert set(config.names) == {"omsk_machines", "cn_export_grain"}

    def test_get_existing(self, campaigns_file: Path):
        config = load_campaigns(campaigns_file)
        campaign = config.get("omsk_machines")
        assert campaign.niche_name == "Промышленное оборудование"
        assert campaign.language == "ru"
        assert campaign.countries == ["Russia"]
        assert campaign.direction == "import"

    def test_get_missing_raises(self, campaigns_file: Path):
        config = load_campaigns(campaigns_file)
        with pytest.raises(CampaignError):
            config.get("nope")

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(CampaignError):
            load_campaigns(tmp_path / "absent.yaml")

    def test_no_campaigns_raises(self, tmp_path: Path):
        path = tmp_path / "empty.yaml"
        path.write_text("campaigns: {}\n", encoding="utf-8")
        with pytest.raises(CampaignError):
            load_campaigns(path)

    def test_invalid_language_raises(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text(
            CAMPAIGN_YAML.replace("language: ru", "language: klingon"),
            encoding="utf-8",
        )
        with pytest.raises(CampaignError):
            load_campaigns(path)


class TestCampaignValidation:
    def test_direction_defaults_to_import(self, campaigns_file: Path):
        config = load_campaigns(campaigns_file)
        assert config.get("omsk_machines").direction == "import"

    def test_rubric_requires_code_and_name(self, tmp_path: Path):
        path = tmp_path / "bad_rubric.yaml"
        path.write_text(
            CAMPAIGN_YAML.replace(
                '- {code: "614", name: "Металлообрабатывающее оборудование"}',
                '- {code: "614"}',
            ),
            encoding="utf-8",
        )
        with pytest.raises(CampaignError):
            load_campaigns(path)

    def test_city_codes_lowercased(self, campaigns_file: Path):
        config = load_campaigns(campaigns_file)
        campaign = config.get("omsk_machines")
        assert campaign.gis2_cities == ["omsk", "novosibirsk"]


class TestProfileGeneration:
    def test_to_profile(self, campaigns_file: Path):
        campaign = load_campaigns(campaigns_file).get("omsk_machines")
        profile = campaign.to_profile()
        assert profile.name == "omsk_machines"
        assert profile.keywords_en == ["machine tool", "cnc machine"]
        assert profile.language == "ru"
        assert profile.countries == ["Russia"]
        assert profile.direction == "import"
        assert profile.hs_codes == ["8456"]

    def test_keywords_ru_folded_into_keywords_zh_slot(self, campaigns_file: Path):
        """Русские ключи ложатся в keywords_zh: слот «не-латиница», регистронезависимо."""
        campaign = load_campaigns(campaigns_file).get("omsk_machines")
        profile = campaign.to_profile()
        assert "станки" in profile.keywords_zh


class TestGis2TargetGeneration:
    def test_targets_are_city_x_rubric(self, campaigns_file: Path):
        campaign = load_campaigns(campaigns_file).get("omsk_machines")
        targets = campaign.to_gis2_targets()
        assert len(targets) == 2  # 2 города
        for target in targets:
            assert isinstance(target, Gis2Target)
            assert target.country == "Russia"
            assert target.domain == "ru"
            assert {r["code"] for r in target.rubrics} == {"614", "112"}

    def test_no_gis2_section_gives_no_targets(self, campaigns_file: Path):
        campaign = load_campaigns(campaigns_file).get("cn_export_grain")
        assert campaign.gis2_cities == []
        assert campaign.to_gis2_targets() == []

    def test_country_from_campaign_not_section(self, campaigns_file: Path):
        """Страна цели берётся из countries кампании (первая), не из секции gis2."""
        campaign = load_campaigns(campaigns_file).get("omsk_machines")
        targets = campaign.to_gis2_targets()
        assert all(t.country == "Russia" for t in targets)


class TestCampaignDataclass:
    def test_has_campaign_id(self, campaigns_file: Path):
        campaign = load_campaigns(campaigns_file).get("omsk_machines")
        assert campaign.name == "omsk_machines"

    def test_limits_loaded(self, campaigns_file: Path):
        config = load_campaigns(campaigns_file)
        assert config.limits.request_delay_seconds == 3.0
        assert config.limits.max_concurrency == 2
