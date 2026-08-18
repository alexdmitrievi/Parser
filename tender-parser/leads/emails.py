"""Извлечение почтовых адресов со страниц компании.

Что делает модуль:

* тянет адреса из ``mailto:`` и из текста страницы регуляркой;
* раскрывает обфускацию: ``name (at) domain (dot) com``, ``name[at]domain[dot]com``,
  ``name#domain.com``, ``name AT domain DOT com``;
* отсеивает мусор: ``noreply@``, ``@example.com``, трекеры, плейсхолдеры,
  адреса, вшитые в имена файлов картинок;
* классифицирует ``role`` (info@, sales@, export@…) против ``personal``;
* приводит к нижнему регистру и дедуплицирует по паре (домен, локальная часть);
* для каждого адреса запоминает URL страницы, откуда он снят.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote, urlsplit

from leads.models import EMAIL_KIND_PERSONAL, EMAIL_KIND_ROLE, ROLE_LOCAL_PARTS, LeadEmail, utcnow

# ── Мусорные адреса ──

# Локальные части, которые никогда не являются контактом для рассылки.
JUNK_LOCAL_PARTS = frozenset({
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "postmaster", "mailer-daemon", "bounce", "bounces", "abuse",
    "example", "test", "sample", "demo", "your", "youremail", "your-email",
    "name", "yourname", "email", "user", "username", "someone", "somebody",
    "firstname", "lastname", "john.doe", "jane.doe", "foo", "bar",
    "sentry", "webmaster@localhost",
})

# Домены, чьи адреса — телеметрия, шаблоны и хостинг, а не живые контакты.
JUNK_DOMAINS = frozenset({
    "example.com", "example.org", "example.net", "example.edu",
    "domain.com", "yourdomain.com", "mydomain.com", "yoursite.com",
    "email.com", "mail.com", "test.com", "sample.com", "company.com",
    "sentry.io", "sentry-cdn.com", "wixpress.com", "wix.com",
    "localhost", "localhost.localdomain", "godaddy.com", "squarespace.com",
    "schema.org", "w3.org", "sentry.wixpress.com",
})

# Подстроки в домене, выдающие технический адрес.
JUNK_DOMAIN_MARKERS = ("sentry", "wixpress", ".local", ".invalid", ".test", ".example")

# Расширения файлов: 'logo@2x.png' и 'icon@2x.jpg' ловятся общей регуляркой.
IMAGE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".mp4",
    ".html", ".htm", ".php", ".aspx", ".jsp", ".xml", ".json",
)

# ── Регулярные выражения ──

# Обычный адрес. Локальная часть без ведущей/замыкающей точки.
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~\-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~\-]+)*"
    r"@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,24}"
)

# Валидация уже собранного адреса целиком.
_EMAIL_FULL_RE = re.compile(rf"^{_EMAIL_RE.pattern}$")

# Обфускация разбирается двумя отдельными шаблонами, а не одним общим.
#
# Символьные разделители — ``(at)``, ``[at]``, ``{at}``, ``#``, ``&#64;`` — сами
# по себе однозначны, поэтому точку рядом с ними можно принимать в любом виде.
#
# Словесные ``at``/``dot`` однозначны только парой: если принимать `` at `` с
# обычной точкой, то «look at google.com» превратится в look@google.com.
# Поэтому в словесном шаблоне точка тоже обязана быть словом.
_LOCAL = r"([A-Za-z0-9._%+\-]+)"
_TLD = r"([A-Za-z]{2,24})"

_AT_SYMBOLIC = r"\s*(?:\(\s*at\s*\)|\[\s*at\s*\]|\{\s*at\s*\}|&#64;|%40|#)\s*"
_DOT_SYMBOLIC = r"\s*(?:\(\s*dot\s*\)|\[\s*dot\s*\]|\{\s*dot\s*\}|&#46;|\.)\s*"
_AT_SPELLED = r"\s+at\s+"
_DOT_SPELLED = r"\s+dot\s+"


def _obfuscated_pattern(at_token: str, dot_token: str) -> re.Pattern[str]:
    """Собрать шаблон ``local AT label (DOT label)* DOT tld``."""
    return re.compile(
        _LOCAL
        + at_token
        + r"([A-Za-z0-9\-]+(?:" + dot_token + r"[A-Za-z0-9\-]+)*)"
        + dot_token
        + _TLD,
        re.IGNORECASE,
    )


_OBFUSCATED_PATTERNS = (
    _obfuscated_pattern(_AT_SYMBOLIC, _DOT_SYMBOLIC),
    _obfuscated_pattern(_AT_SPELLED, _DOT_SPELLED),
)

_MAILTO_RE = re.compile(r"""mailto:\s*([^"'\s>?]+)""", re.IGNORECASE)

_DEOBF_DOT_RE = re.compile(r"\(\s*dot\s*\)|\[\s*dot\s*\]|\{\s*dot\s*\}|\s+dot\s+|&#46;", re.IGNORECASE)
_DEOBF_AT_RE = re.compile(r"\(\s*at\s*\)|\[\s*at\s*\]|\{\s*at\s*\}|\s+at\s+|&#64;|%40", re.IGNORECASE)


def deobfuscate(text: str) -> str:
    """Развернуть текстовую обфускацию адресов в обычный вид.

        >>> deobfuscate("sales (at) example (dot) cn")
        'sales@example.cn'
    """
    if not text:
        return ""
    result = _DEOBF_DOT_RE.sub(".", text)
    result = _DEOBF_AT_RE.sub("@", result)
    # Схлопываем пробелы вокруг разделителей: "sales @ example . cn"
    result = re.sub(r"\s*@\s*", "@", result)
    result = re.sub(r"\s*\.\s*", ".", result)
    return result


def normalize_email(raw: str) -> str:
    """Привести адрес к канонической форме или вернуть '' если он невалиден."""
    if not raw:
        return ""

    candidate = unescape(unquote(raw.strip()))
    candidate = candidate.strip().strip("<>\"'()[]{},;:")
    # Хвост querystring из mailto:
    candidate = candidate.split("?", 1)[0]
    candidate = candidate.replace(" ", "").lower()

    if candidate.count("@") != 1:
        return ""
    if not _EMAIL_FULL_RE.match(candidate):
        return ""
    return candidate


def is_junk(email: str) -> bool:
    """True для служебных, шаблонных и заведомо непригодных адресов."""
    if not email or "@" not in email:
        return True

    local, domain = email.split("@", 1)

    if domain in JUNK_DOMAINS:
        return True
    if any(marker in domain for marker in JUNK_DOMAIN_MARKERS):
        return True
    if local in JUNK_LOCAL_PARTS:
        return True
    if local.startswith(("noreply", "no-reply", "no_reply", "donotreply", "do-not-reply")):
        return True
    # 'logo@2x.png' и прочие имена файлов
    if email.endswith(IMAGE_EXTENSIONS):
        return True
    # Хэши из вёрстки: длинная бессмысленная локальная часть без гласных
    if len(local) > 40:
        return True
    # Домен верхнего уровня из одного сегмента отсеян регуляркой, но проверим
    if "." not in domain:
        return True
    return False


def classify(email: str) -> str:
    """``role`` для обезличенных ящиков, ``personal`` для именных.

    Ролевым считается адрес, у которого локальная часть — известное служебное
    слово, возможно с цифровым или разделённым суффиксом: ``sales2@``,
    ``export-cn@``, ``info.hk@``.
    """
    if not email or "@" not in email:
        return EMAIL_KIND_PERSONAL

    local = email.split("@", 1)[0]

    if local in ROLE_LOCAL_PARTS:
        return EMAIL_KIND_ROLE

    # sales2 / export01 — служебное слово с числовым суффиксом
    stripped = local.rstrip("0123456789")
    if stripped and stripped in ROLE_LOCAL_PARTS:
        return EMAIL_KIND_ROLE

    # sales-cn / info.hk / export_2 — первый сегмент служебный
    for separator in (".", "-", "_"):
        if separator in local:
            head = local.split(separator, 1)[0].rstrip("0123456789")
            if head in ROLE_LOCAL_PARTS:
                return EMAIL_KIND_ROLE

    return EMAIL_KIND_PERSONAL


def extract_emails(html: str, source_url: str = "") -> list[LeadEmail]:
    """Собрать адреса со страницы.

    Args:
        html: HTML или текст страницы.
        source_url: URL страницы — сохраняется в каждом найденном адресе,
            чтобы находку можно было проверить руками.

    Returns:
        Уникальные валидные адреса, дедуплицированные по (домен, локальная часть),
        в порядке первого появления на странице.
    """
    if not html:
        return []

    found: dict[str, LeadEmail] = {}
    now = utcnow()

    def remember(raw: str) -> None:
        email = normalize_email(raw)
        if not email or is_junk(email):
            return
        if email in found:
            return
        found[email] = LeadEmail(
            email=email,
            kind=classify(email),
            source_url=source_url,
            first_seen=now,
            last_seen=now,
        )

    # 1. mailto: — самый надёжный источник.
    for match in _MAILTO_RE.finditer(html):
        remember(match.group(1))

    # 2. Обычные адреса в тексте и атрибутах.
    text = unescape(html)
    for match in _EMAIL_RE.finditer(text):
        remember(match.group(0))

    # 3. Обфусцированные записи.
    for pattern in _OBFUSCATED_PATTERNS:
        for match in pattern.finditer(text):
            local, domain_body, tld = match.groups()
            candidate = f"{local}@{deobfuscate(domain_body)}.{tld}"
            remember(candidate)

    return list(found.values())


def emails_for_domain(emails: list[LeadEmail], domain: str) -> list[LeadEmail]:
    """Оставить только адреса на домене компании (или его поддоменах).

    Страница контактов часто содержит адреса подрядчиков, разработчиков сайта
    и партнёров — они компании не принадлежат.
    """
    if not domain:
        return list(emails)

    target = domain.lower().removeprefix("www.")
    kept: list[LeadEmail] = []
    for item in emails:
        candidate = item.domain
        if candidate == target or candidate.endswith("." + target):
            kept.append(item)
    return kept


def domain_from_url(url: str) -> str:
    """Хост из URL без ``www.`` — для сопоставления адресов с сайтом."""
    if not url:
        return ""
    try:
        host = urlsplit(url if "//" in url else "//" + url).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


__all__ = [
    "extract_emails",
    "normalize_email",
    "deobfuscate",
    "is_junk",
    "classify",
    "emails_for_domain",
    "domain_from_url",
    "JUNK_LOCAL_PARTS",
    "JUNK_DOMAINS",
    "EMAIL_KIND_ROLE",
    "EMAIL_KIND_PERSONAL",
]
