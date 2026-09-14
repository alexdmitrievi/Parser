"""XML extraction for SOAP, RSS, EIS FTP feeds."""

from __future__ import annotations

import re
from typing import Any, Optional
from xml.etree import ElementTree as ET

from engine.parsers.utils import clean_text
from engine.observability.logger import get_logger

logger = get_logger("parser.xml")


class XmlExtractor:
    """XML parser with namespace-aware element lookup and fallback chains."""

    # Common EIS namespaces
    DEFAULT_NAMESPACES = {
        "ns": "http://zakupki.gov.ru/oos/types/1",
        "ns2": "http://zakupki.gov.ru/oos/export/1",
        "ns3": "http://zakupki.gov.ru/oos/printform/1",
        "oos": "http://zakupki.gov.ru/oos/types/1",
    }

    def __init__(self, namespaces: dict[str, str] | None = None):
        self._ns = namespaces or {}

    def parse(self, xml_content: str) -> ET.Element | None:
        """Parse XML string, return root element."""
        try:
            # Remove XML declaration encoding issues
            xml_content = re.sub(r'<\?xml[^?]+\?>', '', xml_content, count=1)
            return ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.warning(f"XML parse error: {e}")
            return None

    def find(
        self,
        element: ET.Element,
        tags: str | list[str],
        namespaces: dict[str, str] | None = None,
    ) -> ET.Element | None:
        """Find first matching child element with namespace fallbacks.

        Args:
            element: Parent element
            tags: Tag name or list of tag names to try
            namespaces: Optional namespace map override
        """
        ns = namespaces or self._ns
        if isinstance(tags, str):
            tags = [tags]

        for tag in tags:
            # Try with each namespace prefix
            for prefix, uri in ns.items():
                el = element.find(f"{{{uri}}}{tag}")
                if el is not None:
                    return el

            # Try without namespace
            el = element.find(tag)
            if el is not None:
                return el

            # Try with wildcard namespace
            el = element.find(f".//{tag}")
            if el is not None:
                return el

        return None

    def find_text(
        self,
        element: ET.Element,
        tags: str | list[str],
        namespaces: dict[str, str] | None = None,
        default: str = "",
    ) -> str:
        """Find element and return its text content."""
        el = self.find(element, tags, namespaces)
        if el is not None and el.text:
            return clean_text(el.text)
        return default

    def find_all(
        self,
        element: ET.Element,
        tag: str,
        namespaces: dict[str, str] | None = None,
    ) -> list[ET.Element]:
        """Find all matching elements."""
        ns = namespaces or self._ns
        results: list[ET.Element] = []

        for prefix, uri in ns.items():
            found = element.findall(f".//{{{uri}}}{tag}")
            if found:
                return found

        found = element.findall(f".//{tag}")
        if found:
            return found

        return results

    def extract_record(
        self,
        element: ET.Element,
        field_tags: dict[str, str | list[str]],
        namespaces: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Extract fields from an XML element using tag mapping.

        Args:
            element: XML element
            field_tags: Map of field_name -> tag name(s) to try
            namespaces: Namespace map
        """
        record: dict[str, Any] = {}

        for field_name, tags in field_tags.items():
            text = self.find_text(element, tags, namespaces)
            if text:
                record[field_name] = text

        return record
