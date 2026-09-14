"""Нормализация полей карточки компании.

Отвечает за приведение к канонической форме того, по чему потом идёт
дедупликация: домен сайта и название компании. Плюс определение провинции и
города по свободному тексту адреса.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from engine.parsers.utils import clean_text

# ── Домены ──

# Хосты, которые не являются сайтом компании: агрегаторы, соцсети, почтовики.
# Если "сайт" компании указывает сюда — это не её домен, дедуп по нему нельзя.
NON_COMPANY_HOSTS = frozenset({
    "made-in-china.com", "alibaba.com", "1688.com", "aliexpress.com",
    "globalsources.com", "ec21.com", "tradeindia.com", "indiamart.com",
    "facebook.com", "linkedin.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "weibo.com", "wechat.com", "qq.com", "tiktok.com",
    "google.com", "baidu.com", "bing.com", "wikipedia.org",
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "163.com",
    "126.com", "sina.com", "foxmail.com", "aliyun.com",
})

# Юридические формы — вычищаются из ключа дедупликации по названию.
_LEGAL_SUFFIXES = (
    "co ltd", "co limited", "company limited", "company ltd", "corporation",
    "incorporated", "international", "industrial", "industry", "technology",
    "trading", "trade", "group", "holdings", "holding", "limited", "ltd",
    "llc", "inc", "corp", "plc", "gmbh", "co",
)

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[.,;:!?'\"“”‘’()\[\]{}·、，。\-－—–_/\\|]+")
_CJK_RE = re.compile(r"[一-鿿㐀-䶿]")


def has_cjk(text: str) -> bool:
    """Есть ли в строке китайские иероглифы."""
    return bool(_CJK_RE.search(text or ""))


def normalize_domain(value: str) -> str:
    """Привести URL или домен к каноническому виду.

    Убирает схему, ``www.``, порт, путь, параметры и завершающую точку.
    Возвращает пустую строку, если домена нет или он невалиден.

        >>> normalize_domain("https://WWW.Example.COM:443/contact?x=1")
        'example.com'
    """
    if not value:
        return ""

    raw = value.strip().strip("<>\"'").lower()
    if not raw:
        return ""

    if "@" in raw and "//" not in raw:
        # Похоже на адрес почты — берём домен из него.
        raw = raw.split("@", 1)[1]

    if "//" not in raw:
        raw = "//" + raw

    try:
        host = urlsplit(raw).hostname or ""
    except ValueError:
        return ""

    host = host.strip(".").removeprefix("www.")

    # Домен должен содержать точку и допустимые символы.
    if "." not in host or not re.fullmatch(r"[a-z0-9.\-]+", host):
        return ""
    if host.endswith(".") or ".." in host:
        return ""

    return host


def is_company_domain(domain: str) -> bool:
    """False для агрегаторов, соцсетей и публичных почтовиков."""
    if not domain:
        return False
    if domain in NON_COMPANY_HOSTS:
        return False
    # Поддомен агрегатора тоже не считается сайтом компании.
    parts = domain.split(".")
    for i in range(1, len(parts)):
        if ".".join(parts[i:]) in NON_COMPANY_HOSTS:
            return False
    return True


def normalize_website(value: str) -> str:
    """Канонический URL сайта: ``https://<domain>``. Пусто, если домена нет."""
    domain = normalize_domain(value)
    return f"https://{domain}" if domain else ""


# ── Названия ──

def normalize_company_name(name: str) -> str:
    """Почистить название для отображения: пробелы, кавычки, хвостовая пунктуация."""
    cleaned = clean_text(name or "")
    cleaned = _WS_RE.sub(" ", cleaned).strip(" -–—|,;:")
    return cleaned


def company_name_key(name: str) -> str:
    """Ключ дедупликации по названию.

    Нижний регистр, без пунктуации и юридических форм, пробелы схлопнуты.

        >>> company_name_key("Shandong Petro-Coke Co., Ltd.")
        'shandong petro coke'
    """
    if not name:
        return ""

    key = _PUNCT_RE.sub(" ", name.lower())
    key = _WS_RE.sub(" ", key).strip()

    # Юридические формы могут идти подряд ("... industrial co ltd").
    changed = True
    while changed:
        changed = False
        for suffix in _LEGAL_SUFFIXES:
            if key.endswith(" " + suffix):
                key = key[: -len(suffix) - 1].strip()
                changed = True
    return key


def split_name_by_script(name: str) -> tuple[str, str]:
    """Разделить название на латинскую и китайскую части.

    Каталоги часто дают их одной строкой: ``山东宏运 Shandong Hongyun Co., Ltd``.
    Возвращает ``(en, zh)``; пустая строка, если части нет.
    """
    cleaned = normalize_company_name(name)
    if not cleaned:
        return "", ""
    if not has_cjk(cleaned):
        return cleaned, ""

    zh_chars = _CJK_RE.findall(cleaned)
    if len(zh_chars) == len(cleaned.replace(" ", "")):
        return "", cleaned

    # Смешанная строка: китайские фрагменты отдельно, остальное — латиница.
    zh_parts = re.findall(r"[一-鿿㐀-䶿（）()·]+", cleaned)
    en_part = _CJK_RE.sub(" ", cleaned)
    en_part = re.sub(r"[（）]", " ", en_part)
    return normalize_company_name(en_part), normalize_company_name("".join(zh_parts))


# ── География ──

# (маркер в тексте, каноническая провинция). Латиница и иероглифы.
_PROVINCES: list[tuple[str, str]] = [
    ("heilongjiang", "Heilongjiang"), ("黑龙江", "Heilongjiang"),
    ("inner mongolia", "Inner Mongolia"), ("nei mongol", "Inner Mongolia"), ("内蒙古", "Inner Mongolia"),
    ("guangdong", "Guangdong"), ("广东", "Guangdong"),
    ("guangxi", "Guangxi"), ("广西", "Guangxi"),
    ("shandong", "Shandong"), ("山东", "Shandong"),
    ("shanghai", "Shanghai"), ("上海", "Shanghai"),
    ("shaanxi", "Shaanxi"), ("陕西", "Shaanxi"),
    ("shanxi", "Shanxi"), ("山西", "Shanxi"),
    ("sichuan", "Sichuan"), ("四川", "Sichuan"),
    ("chongqing", "Chongqing"), ("重庆", "Chongqing"),
    ("liaoning", "Liaoning"), ("辽宁", "Liaoning"),
    ("zhejiang", "Zhejiang"), ("浙江", "Zhejiang"),
    ("jiangsu", "Jiangsu"), ("江苏", "Jiangsu"),
    ("jiangxi", "Jiangxi"), ("江西", "Jiangxi"),
    ("xinjiang", "Xinjiang"), ("新疆", "Xinjiang"),
    ("ningxia", "Ningxia"), ("宁夏", "Ningxia"),
    ("qinghai", "Qinghai"), ("青海", "Qinghai"),
    ("guizhou", "Guizhou"), ("贵州", "Guizhou"),
    ("yunnan", "Yunnan"), ("云南", "Yunnan"),
    ("hunan", "Hunan"), ("湖南", "Hunan"),
    ("hubei", "Hubei"), ("湖北", "Hubei"),
    ("henan", "Henan"), ("河南", "Henan"),
    ("hebei", "Hebei"), ("河北", "Hebei"),
    ("hainan", "Hainan"), ("海南", "Hainan"),
    ("gansu", "Gansu"), ("甘肃", "Gansu"),
    ("fujian", "Fujian"), ("福建", "Fujian"),
    ("anhui", "Anhui"), ("安徽", "Anhui"),
    ("beijing", "Beijing"), ("北京", "Beijing"),
    ("tianjin", "Tianjin"), ("天津", "Tianjin"),
    ("jilin", "Jilin"), ("吉林", "Jilin"),
    ("tibet", "Tibet"), ("xizang", "Tibet"), ("西藏", "Tibet"),
    ("hong kong", "Hong Kong"), ("hongkong", "Hong Kong"), ("香港", "Hong Kong"),
    ("macau", "Macau"), ("macao", "Macau"), ("澳门", "Macau"),
    ("taiwan", "Taiwan"), ("台湾", "Taiwan"),
]
# Длинные маркеры первыми, иначе "shanxi" перехватит "shaanxi"-подобные случаи.
_PROVINCES.sort(key=lambda pair: len(pair[0]), reverse=True)

# Промышленные города → провинция. Помогает, когда провинция не указана явно.
_CITIES: list[tuple[str, str, str]] = [
    ("qingdao", "Qingdao", "Shandong"), ("青岛", "Qingdao", "Shandong"),
    ("yantai", "Yantai", "Shandong"), ("烟台", "Yantai", "Shandong"),
    ("weifang", "Weifang", "Shandong"), ("潍坊", "Weifang", "Shandong"),
    ("zibo", "Zibo", "Shandong"), ("淄博", "Zibo", "Shandong"),
    ("rizhao", "Rizhao", "Shandong"), ("日照", "Rizhao", "Shandong"),
    ("dongying", "Dongying", "Shandong"), ("东营", "Dongying", "Shandong"),
    ("jinan", "Jinan", "Shandong"), ("济南", "Jinan", "Shandong"),
    ("linyi", "Linyi", "Shandong"), ("临沂", "Linyi", "Shandong"),
    ("tangshan", "Tangshan", "Hebei"), ("唐山", "Tangshan", "Hebei"),
    ("handan", "Handan", "Hebei"), ("邯郸", "Handan", "Hebei"),
    ("shijiazhuang", "Shijiazhuang", "Hebei"), ("石家庄", "Shijiazhuang", "Hebei"),
    ("cangzhou", "Cangzhou", "Hebei"), ("沧州", "Cangzhou", "Hebei"),
    ("zhengzhou", "Zhengzhou", "Henan"), ("郑州", "Zhengzhou", "Henan"),
    ("luoyang", "Luoyang", "Henan"), ("洛阳", "Luoyang", "Henan"),
    ("gongyi", "Gongyi", "Henan"), ("巩义", "Gongyi", "Henan"),
    ("dalian", "Dalian", "Liaoning"), ("大连", "Dalian", "Liaoning"),
    ("shenyang", "Shenyang", "Liaoning"), ("沈阳", "Shenyang", "Liaoning"),
    ("fushun", "Fushun", "Liaoning"), ("抚顺", "Fushun", "Liaoning"),
    ("jinzhou", "Jinzhou", "Liaoning"), ("锦州", "Jinzhou", "Liaoning"),
    ("nanjing", "Nanjing", "Jiangsu"), ("南京", "Nanjing", "Jiangsu"),
    ("suzhou", "Suzhou", "Jiangsu"), ("苏州", "Suzhou", "Jiangsu"),
    ("wuxi", "Wuxi", "Jiangsu"), ("无锡", "Wuxi", "Jiangsu"),
    ("lianyungang", "Lianyungang", "Jiangsu"), ("连云港", "Lianyungang", "Jiangsu"),
    ("xuzhou", "Xuzhou", "Jiangsu"), ("徐州", "Xuzhou", "Jiangsu"),
    ("urumqi", "Urumqi", "Xinjiang"), ("乌鲁木齐", "Urumqi", "Xinjiang"),
    ("karamay", "Karamay", "Xinjiang"), ("克拉玛依", "Karamay", "Xinjiang"),
    ("chengdu", "Chengdu", "Sichuan"), ("成都", "Chengdu", "Sichuan"),
    ("panzhihua", "Panzhihua", "Sichuan"), ("攀枝花", "Panzhihua", "Sichuan"),
    ("ningbo", "Ningbo", "Zhejiang"), ("宁波", "Ningbo", "Zhejiang"),
    ("hangzhou", "Hangzhou", "Zhejiang"), ("杭州", "Hangzhou", "Zhejiang"),
    ("guangzhou", "Guangzhou", "Guangdong"), ("广州", "Guangzhou", "Guangdong"),
    ("shenzhen", "Shenzhen", "Guangdong"), ("深圳", "Shenzhen", "Guangdong"),
    ("foshan", "Foshan", "Guangdong"), ("佛山", "Foshan", "Guangdong"),
]
_CITIES.sort(key=lambda triple: len(triple[0]), reverse=True)


def detect_province(text: str) -> str:
    """Определить китайскую провинцию по свободному тексту. '' если не найдена."""
    if not text:
        return ""
    lowered = text.lower()
    for marker, province in _PROVINCES:
        if marker in lowered:
            return province
    # Провинция не названа — пробуем вывести из города.
    for marker, _city, province in _CITIES:
        if marker in lowered:
            return province
    return ""


def detect_city(text: str) -> str:
    """Определить город по свободному тексту. '' если не найден."""
    if not text:
        return ""
    lowered = text.lower()
    for marker, city, _province in _CITIES:
        if marker in lowered:
            return city
    return ""


def parse_location(text: str) -> tuple[str, str]:
    """Вернуть ``(province, city)`` для строки адреса."""
    return detect_province(text), detect_city(text)


__all__ = [
    "normalize_domain",
    "normalize_website",
    "is_company_domain",
    "normalize_company_name",
    "company_name_key",
    "split_name_by_script",
    "detect_province",
    "detect_city",
    "parse_location",
    "has_cjk",
    "NON_COMPANY_HOSTS",
]
