"""Извлечение вида деятельности, предложений и запросов с сайта компании.

Третий результат обогащения после почт и контактов: из текста страниц достаём
(1) краткое описание того, чем компания занимается, (2) фразы о том, что она
предлагает (производит/продаёт/экспортирует), и (3) фразы о том, что она ищет
(импортирует/закупает).

Эвристика намеренно простая и консервативная: лучше вернуть меньше, но по
делу, чем натащить мусора из футера, меню и куки-баннеров.
"""

from __future__ import annotations

import re

# Глаголы-маркеры «мы предлагаем» (производство/поставка/экспорт).
_OFFER_MARKERS = (
    "manufactur", "produc", "suppli", "export", "wholesal", "oem",
    "specializ", "sell", "distribut",
)

# Глаголы-маркеры «мы ищем» (импорт/закупка/потребность).
_REQUEST_MARKERS = (
    "import", "purchas", "procur", "sourc", "look for", "looking for",
    "seek", "inquir",
)

_MAX_PHRASE_LEN = 220

# Разбивка на предложения по концам предложений (точка, !, ?, китайские знаки).
_SENTENCE_RE = re.compile(r"[^.!?。！？\n]+[.!?。！？]?")


def _split_sentences(text: str) -> list[str]:
    """Разбить видимый текст на предложения, отбросив слишком короткие."""
    if not text:
        return []
    sentences: list[str] = []
    for part in _SENTENCE_RE.findall(text):
        phrase = " ".join(part.split())
        if len(phrase) >= 12:
            sentences.append(phrase)
    return sentences


def _clean(phrase: str) -> str:
    phrase = " ".join(phrase.split())
    if len(phrase) > _MAX_PHRASE_LEN:
        phrase = phrase[:_MAX_PHRASE_LEN].rstrip() + "…"
    return phrase


def _phrases_with(text: str, markers: tuple[str, ...], limit: int) -> list[str]:
    found: list[str] = []
    for sentence in _split_sentences(text):
        low = sentence.lower()
        if not any(marker in low for marker in markers):
            continue
        phrase = _clean(sentence)
        if phrase and phrase not in found:
            found.append(phrase)
        if len(found) >= limit:
            break
    return found


def extract_offers(text: str, limit: int = 10) -> list[str]:
    """Фразы о том, что компания предлагает (производит/поставляет/экспортирует).

    Args:
        text: Видимый текст страницы.
        limit: Максимальное число фраз.

    Returns:
        Уникальные фразы в порядке появления, каждая не длиннее 220 символов.
    """
    return _phrases_with(text, _OFFER_MARKERS, limit)


def extract_requests(text: str, limit: int = 10) -> list[str]:
    """Фразы о том, что компания ищет (импортирует/закупает/нуждается)."""
    return _phrases_with(text, _REQUEST_MARKERS, limit)


def extract_activity(text: str, max_len: int = 300) -> str:
    """Краткое описание деятельности — первые 1–2 осмысленных предложения.

    Args:
        text: Видимый текст страницы (главной или «о нас»).
        max_len: Предельная длина результата.

    Returns:
        Строка из первых предложений либо пустая строка.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return ""
    joined = " ".join(sentences[:2])
    return joined[:max_len].rstrip() + ("…" if len(joined) > max_len else "")


__all__ = ["extract_activity", "extract_offers", "extract_requests"]
