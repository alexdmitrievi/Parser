"""Сопоставление ключевых слов ниш с текстом тендера.

Раньше оба тегера искали ключевое слово простой подстрокой (``kw in text``).
Для длинных слов это удобно — «мебель» находится в «мебельный». Но для коротких
аббревиатур из пресетов это давало массовые ложные срабатывания:

    «моло**чн**ых проду**кт**ов»  → medical  (КТ), transport (ТО)
    «объе**кт**а»                 → medical  (КТ)
    «в слу**чай**е»               → food     (чай)
    «пе**сок**»                   → food     (сок)
    «с**порт**ивный»              → transport (порт)
    «э**кран**»                   → construction (кран)
    «комисс**ии**»                → it       (ИИ)

Теги ниш управляют матчингом подписок в боте, поэтому мусорные теги
превращались в нерелевантные уведомления пользователям.

Решение: ключевое слово должно начинаться на границе слова. Совпадение внутри
слова не считается, а совпадение с начала — считается, так что полезное
поведение «мебель» → «мебельный» сохраняется:

    >>> matches("мебель", "поставка мебельной фурнитуры")
    True
    >>> matches("КТ", "поставка молочных продуктов")
    False
    >>> matches("КТ", "аппарат КТ для больницы")
    True
"""

from __future__ import annotations

import re
from functools import lru_cache

# ``(?<!\w)`` — предыдущий символ не буква/цифра/подчёркивание. Работает и с
# кириллицей: в Python 3 \w для str по умолчанию юникодный.
_BOUNDARY = r"(?<!\w)"


@lru_cache(maxsize=4096)
def _compile(keyword: str) -> re.Pattern[str]:
    """Скомпилировать шаблон «ключевое слово с начала слова»."""
    return re.compile(_BOUNDARY + re.escape(keyword.lower()))


def matches(keyword: str, text: str) -> bool:
    """Встречается ли ключевое слово в тексте, начинаясь на границе слова."""
    if not keyword or not text:
        return False
    return _compile(keyword).search(text.lower()) is not None


def any_matches(keywords: list[str], text: str) -> bool:
    """Совпало ли хотя бы одно ключевое слово."""
    if not text:
        return False
    lowered = text.lower()
    return any(_compile(k).search(lowered) for k in keywords if k)


def matched_keywords(keywords: list[str], text: str) -> list[str]:
    """Список совпавших ключевых слов — для отладки и объяснения тега."""
    if not text:
        return []
    lowered = text.lower()
    return [k for k in keywords if k and _compile(k).search(lowered)]


def okpd2_matches(codes: list[str], prefixes: list[str]) -> bool:
    """Совпадает ли хотя бы один код ОКПД2 с одним из префиксов ниши."""
    return any(code.startswith(prefix) for code in codes for prefix in prefixes)


__all__ = ["matches", "any_matches", "matched_keywords", "okpd2_matches"]
