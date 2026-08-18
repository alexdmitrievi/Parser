"""Тесты сопоставления ключевых слов ниш.

Регрессия, ради которой они написаны: короткие аббревиатуры из пресетов
(«КТ», «ТО», «ИИ», «сок», «порт», «кран», «чай») искались простой подстрокой
и ловились внутри обычных слов. Почти каждый тендер получал мусорные теги,
а теги ниш управляют матчингом подписок в боте — то есть люди получали
нерелевантные уведомления.
"""

from __future__ import annotations

import pytest

from shared.keyword_match import any_matches, matched_keywords, matches, okpd2_matches


class TestWordBoundary:
    @pytest.mark.parametrize(
        "keyword,text",
        [
            ("КТ", "поставка молочных продуктов"),
            ("КТ", "оказание услуг по охране объекта"),
            ("ТО", "поставка молочных продуктов"),
            ("ИИ", "обслуживание территории комиссии"),
            ("ИИ", "работы на линии электропередачи"),
            ("сок", "поставка песка строительного"),
            ("порт", "ремонт спортивного зала"),
            ("кран", "поставка экранов для проектора"),
            ("чай", "в случае аварии"),
            ("рис", "юрисдикция суда"),
        ],
    )
    def test_no_match_inside_a_word(self, keyword, text):
        assert matches(keyword, text) is False

    @pytest.mark.parametrize(
        "keyword,text",
        [
            ("КТ", "аппарат КТ для больницы"),
            ("ТО", "ТО автомобилей"),
            ("сок", "сок яблочный концентрированный"),
            ("порт", "морской порт Владивосток"),
            ("кран", "кран башенный аренда"),
            ("чай", "поставка чай в пакетиках"),
        ],
    )
    def test_matches_at_word_start(self, keyword, text):
        assert matches(keyword, text) is True

    @pytest.mark.parametrize(
        "keyword,text",
        [
            ("мебель", "поставка мебельной фурнитуры"),
            ("подряд", "подрядные работы"),
            ("ремонт", "ремонтные работы кровли"),
            ("кровля", "кровля здания требует ремонта"),
        ],
    )
    def test_prefix_matching_is_preserved(self, keyword, text):
        """Длинные слова по-прежнему ловят словоформы — это полезное поведение."""
        assert matches(keyword, text) is True

    def test_case_insensitive(self):
        assert matches("МЕБЕЛЬ", "поставка мебельной фурнитуры") is True
        assert matches("мебель", "ПОСТАВКА МЕБЕЛЬНОЙ ФУРНИТУРЫ") is True

    def test_empty_inputs(self):
        assert matches("", "текст") is False
        assert matches("слово", "") is False

    def test_keyword_with_special_characters(self):
        """Ключи вроде «ж/д» не должны ломать регулярку."""
        assert matches("ж/д", "ж/д перевозки") is True
        assert matches("ж/д", "перевозки автотранспортом") is False


class TestHelpers:
    def test_any_matches(self):
        assert any_matches(["мебель", "диван"], "поставка диванов") is True
        assert any_matches(["КТ", "МРТ"], "молочных продуктов") is False
        assert any_matches([], "любой текст") is False

    def test_matched_keywords_lists_hits(self):
        hits = matched_keywords(["мебель", "стол", "КТ"], "поставка мебельных столов")
        assert hits == ["мебель", "стол"]

    def test_inflection_that_changes_the_stem_is_not_matched(self):
        """Совпадение идёт по префиксу, а не по лемме.

        «мебели» и «чая» не начинаются с «мебель» / «чай», поэтому не ловятся.
        Так было и до перехода на границы слов — это ограничение подхода,
        а не регрессия.
        """
        assert matches("мебель", "поставка мебели") is False
        assert matches("чай", "поставка чая") is False

    def test_okpd2_matches(self):
        assert okpd2_matches(["31.01.11"], ["31.0"]) is True
        assert okpd2_matches(["43.99"], ["31.0", "41.2"]) is False
        assert okpd2_matches([], ["31.0"]) is False


class TestTaggersAgree:
    """Оба тегера — продакшн и движковый — должны давать одинаковый результат."""

    CASES = [
        ("Поставка молочных продуктов", []),
        ("Оказание услуг по охране объекта", []),
        ("Обслуживание территории комиссии", []),
        ("Поставка экранов для проектора", []),
        ("Поставка мебели офисной", ["furniture"]),
        ("Ремонт кровли школы", ["construction"]),
        ("Аппарат КТ для больницы", ["medical"]),
    ]

    @pytest.mark.parametrize("title,expected", CASES)
    def test_engine_tagger(self, title, expected):
        from engine.pipeline.tagger import NicheTagger

        assert NicheTagger().tag({"title": title, "description": ""}) == sorted(expected)

    @pytest.mark.parametrize("title,expected", CASES)
    def test_production_tagger(self, title, expected):
        from pipeline.tagger import tag_tender
        from shared.models import TenderCreate

        tender = TenderCreate(source_platform="test", title=title)
        assert sorted(tag_tender(tender)) == sorted(expected)
