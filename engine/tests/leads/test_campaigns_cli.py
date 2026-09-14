"""Тесты CLI-команд слоя кампаний (python -m leads campaign …)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from leads.cli import build_parser


CAMPAIGN_YAML = textwrap.dedent("""\
    campaigns:
      omsk_machines:
        niche_name: "Промышленное оборудование"
        keywords_en: ["machine tool"]
        keywords_ru: ["станки"]
        hs_codes: []
        target_industries: ["metalworking"]
        direction: import
        language: ru
        countries: ["Russia"]
        gis2:
          domain: ru
          cities: ["omsk"]
          rubrics:
            - {code: "614", name: "Металлообрабатывающее оборудование"}
    limits:
      request_delay_seconds: 3
""")


class TestCampaignCliParser:
    def test_campaign_list(self):
        parser = build_parser()
        args = parser.parse_args(["campaign", "list"])
        assert args.command == "campaign"
        assert args.campaign_command == "list"

    def test_campaign_run_requires_name(self):
        parser = build_parser()
        args = parser.parse_args(["campaign", "run", "omsk_machines"])
        assert args.campaign_command == "run"
        assert args.name == "omsk_machines"

    def test_campaign_run_options(self):
        parser = build_parser()
        args = parser.parse_args(
            ["campaign", "run", "omsk_machines", "--max-records", "5", "--parser-bin", "/bin/p2g"]
        )
        assert args.max_records == 5
        assert args.parser_bin == "/bin/p2g"

    def test_campaign_subcommand_required(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["campaign"])


class TestCampaignCliRun:
    def test_run_collects_via_gis2(self, tmp_path: Path, monkeypatch):
        """run должен прогнать сгенерированные цели 2ГИС через collect_gis2."""
        from leads import cli as cli_mod

        campaigns_file = tmp_path / "lead_campaigns.yaml"
        campaigns_file.write_text(CAMPAIGN_YAML, encoding="utf-8")

        captured: dict = {}

        class FakeRepo:
            def upsert_companies(self, companies):
                captured["companies"] = companies
                return len(companies), 0

            def close(self):
                pass

        def fake_collect_gis2(targets, repository, *, profile="", parser_bin="parser-2gis", max_records=0):
            captured["targets"] = targets
            captured["profile"] = profile
            return 3, 1

        monkeypatch.setattr(cli_mod, "collect_gis2", fake_collect_gis2)

        class Args:
            campaign_command = "run"
            name = "omsk_machines"
            campaigns_config = str(campaigns_file)
            max_records = 0
            parser_bin = "parser-2gis"

        code = cli_mod._cmd_campaign(Args(), None, FakeRepo())
        assert code == 0
        assert captured["profile"] == "omsk_machines"
        assert len(captured["targets"]) == 1
        assert captured["targets"][0].city_code == "omsk"

    def test_run_without_gis2_section_reports_no_targets(self, tmp_path: Path, monkeypatch):
        from leads import cli as cli_mod

        campaigns_file = tmp_path / "lead_campaigns.yaml"
        campaigns_file.write_text(
            CAMPAIGN_YAML.replace(
                'cities: ["omsk"]', "cities: []"
            ),
            encoding="utf-8",
        )

        called = {"n": 0}

        def fake_collect_gis2(*args, **kwargs):
            called["n"] += 1
            return 0, 0

        monkeypatch.setattr(cli_mod, "collect_gis2", fake_collect_gis2)

        class FakeRepo:
            def upsert_companies(self, companies):
                return 0, 0

            def close(self):
                pass

        class Args:
            campaign_command = "run"
            name = "omsk_machines"
            campaigns_config = str(campaigns_file)
            max_records = 0
            parser_bin = "parser-2gis"

        code = cli_mod._cmd_campaign(Args(), None, FakeRepo())
        assert code == 0
        assert called["n"] == 0  # целей нет — обхода не было
