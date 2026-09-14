"""JSON API response parser."""

from __future__ import annotations

from typing import Any

from engine.parsers.utils import clean_text
from engine.observability.logger import get_logger

logger = get_logger("parser.json")


class JsonExtractor:
    """Extract structured data from JSON API responses."""

    def extract_items(
        self,
        data: Any,
        items_path: str | list[str],
    ) -> list[dict[str, Any]]:
        """Navigate JSON structure to extract list of items.

        Args:
            data: Parsed JSON (dict or list)
            items_path: Dot-separated path like "data.results" or ["data", "results"]
                        Use "." for root (if data itself is a list)
        """
        if isinstance(items_path, str):
            if items_path == ".":
                return data if isinstance(data, list) else []
            items_path = items_path.split(".")

        current = data
        for key in items_path:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                idx = int(key)
                current = current[idx] if idx < len(current) else None
            else:
                return []

            if current is None:
                return []

        return current if isinstance(current, list) else []

    def extract_record(
        self,
        item: dict[str, Any],
        field_map: dict[str, str | list[str]],
    ) -> dict[str, Any]:
        """Map JSON item fields to canonical names.

        Args:
            item: Single JSON item
            field_map: Map of target_field -> source_field(s) to try
                       Supports dot-separated nested access: "customer.name"
        """
        record: dict[str, Any] = {}

        for target_field, source_fields in field_map.items():
            if isinstance(source_fields, str):
                source_fields = [source_fields]

            for src in source_fields:
                value = self._get_nested(item, src)
                if value is not None:
                    if isinstance(value, str):
                        value = clean_text(value)
                    record[target_field] = value
                    break

        return record

    def _get_nested(self, obj: dict, path: str) -> Any:
        """Get nested value by dot-separated path."""
        keys = path.split(".")
        current = obj
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
            if current is None:
                return None
        return current

    def extract_listing(
        self,
        data: Any,
        items_path: str | list[str],
        field_map: dict[str, str | list[str]],
    ) -> list[dict[str, Any]]:
        """Top-level: extract all records from a JSON API response."""
        items = self.extract_items(data, items_path)
        return [self.extract_record(item, field_map) for item in items]
