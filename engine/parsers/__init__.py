"""Parsers: HTML, XML, JSON extraction with shared utilities."""

from engine.parsers.utils import (
    parse_price,
    parse_date,
    parse_registry_number,
    clean_text,
    extract_region_from_text,
)
from engine.parsers.html_parser import HtmlExtractor
from engine.parsers.xml_parser import XmlExtractor
from engine.parsers.json_parser import JsonExtractor

__all__ = [
    "parse_price", "parse_date", "parse_registry_number",
    "clean_text", "extract_region_from_text",
    "HtmlExtractor", "XmlExtractor", "JsonExtractor",
]
