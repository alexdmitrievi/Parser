"""HTML extraction with CSS selectors and fallback chains."""

from __future__ import annotations

from typing import Any, Optional

from bs4 import BeautifulSoup, Tag

from engine.parsers.utils import clean_text, parse_price, parse_date, parse_registry_number
from engine.observability.logger import get_logger

logger = get_logger("parser.html")


class HtmlExtractor:
    """Stateless HTML extractor. Uses selector configs, not hardcoded selectors."""

    def __init__(self, parser: str = "html.parser"):
        self._parser = parser

    def parse(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, self._parser)

    def select_blocks(self, html: str, selectors: str | list[str]) -> list[Tag]:
        """Select listing blocks using CSS selector(s) with fallback.

        Args:
            html: Raw HTML content
            selectors: CSS selector string (comma-separated) or list of selectors
        """
        soup = self.parse(html)

        if isinstance(selectors, list):
            for sel in selectors:
                blocks = soup.select(sel)
                if blocks:
                    return blocks
            return []

        return soup.select(selectors)

    def extract_field(
        self,
        block: Tag,
        selectors: str | list[str],
        attribute: str = "text",
        default: str = "",
    ) -> str:
        """Extract a field from a block using CSS selector(s).

        Args:
            block: BeautifulSoup tag to search within
            selectors: CSS selector(s) — string or list (fallback chain)
            attribute: "text" for text content, "href" for link, or any HTML attribute
            default: Value if nothing found
        """
        if isinstance(selectors, str):
            selectors = [selectors]

        for sel in selectors:
            el = block.select_one(sel)
            if el is None:
                continue

            if attribute == "text":
                text = el.get_text(strip=True)
                if text:
                    return text
            elif attribute == "href":
                href = el.get("href", "")
                if href:
                    return str(href)
            else:
                val = el.get(attribute, "")
                if val:
                    return str(val)

        return default

    def extract_link(
        self,
        block: Tag,
        selectors: str | list[str] = "a",
        base_url: str = "",
    ) -> tuple[str, str]:
        """Extract link text and URL from block.

        Returns (title, url) tuple.
        """
        if isinstance(selectors, str):
            selectors = [selectors]

        for sel in selectors:
            link = block.select_one(sel)
            if link and link.name == "a":
                title = clean_text(link.get_text(strip=True))
                href = link.get("href", "")
                if href and not href.startswith(("http://", "https://")):
                    href = base_url.rstrip("/") + "/" + href.lstrip("/")
                return title, str(href)
            elif link:
                # Selected element is not <a>, look for <a> inside it
                a_tag = link.find("a")
                if a_tag:
                    title = clean_text(a_tag.get_text(strip=True))
                    href = a_tag.get("href", "")
                    if href and not href.startswith(("http://", "https://")):
                        href = base_url.rstrip("/") + "/" + href.lstrip("/")
                    return title, str(href)

        return "", ""

    def extract_record(
        self,
        block: Tag,
        field_selectors: dict[str, str | list[str]],
        base_url: str = "",
    ) -> dict[str, Any]:
        """Extract a full record from a block using a selector map.

        Args:
            block: HTML element containing one record
            field_selectors: Map of field_name -> CSS selector(s)
                Special keys:
                    "_link" -> extracts both title and URL from <a> tag
                    "_table_cols" -> extracts by column index (for table rows)
            base_url: Base URL for relative links

        Returns:
            Extracted fields dict
        """
        record: dict[str, Any] = {}

        # Handle link extraction (title + URL combo)
        if "_link" in field_selectors:
            title, url = self.extract_link(block, field_selectors["_link"], base_url)
            if title:
                record["title"] = title
            if url:
                record["url"] = url
                # Try to extract registry number from URL
                reg_num = parse_registry_number(None, url)
                if reg_num:
                    record["registry_number"] = reg_num

        # Handle table column extraction
        if "_table_cols" in field_selectors:
            cols_map = field_selectors["_table_cols"]
            cells = block.find_all("td")
            if isinstance(cols_map, dict):
                for field_name, col_idx in cols_map.items():
                    if isinstance(col_idx, int) and col_idx < len(cells):
                        text = cells[col_idx].get_text(strip=True)
                        if text:
                            record[field_name] = text

        # Regular field extraction
        for field_name, sel in field_selectors.items():
            if field_name.startswith("_"):
                continue

            value = self.extract_field(block, sel)
            if value:
                record[field_name] = value

        return record

    def extract_listing(
        self,
        html: str,
        block_selectors: str | list[str],
        field_selectors: dict[str, str | list[str]],
        base_url: str = "",
        min_title_length: int = 5,
    ) -> list[dict[str, Any]]:
        """Top-level: extract all records from a listing page.

        Combines select_blocks + extract_record for each block.
        Filters out records without a title.
        """
        blocks = self.select_blocks(html, block_selectors)
        records: list[dict[str, Any]] = []

        for block in blocks:
            record = self.extract_record(block, field_selectors, base_url)
            title = record.get("title", "")
            if len(title) >= min_title_length:
                records.append(record)

        return records
