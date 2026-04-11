"""Change detection and versioning for tender/auction/grant records.

Tracks: field changes, status transitions, deadline updates, document additions.
"""

from __future__ import annotations

from typing import Any

from engine.observability.logger import get_logger

logger = get_logger("pipeline.versioner")

# Fields to track for changes
TRACKED_FIELDS = {
    "title", "description", "status", "nmck", "customer_name",
    "customer_region", "submission_deadline", "auction_date",
    "purchase_method", "law_type", "documents_urls", "contact_info",
}

# Fields that indicate significant updates
SIGNIFICANT_FIELDS = {"status", "nmck", "submission_deadline", "auction_date"}


class ChangeDetector:
    """Detect and catalog changes between existing and incoming records."""

    def detect_changes(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, tuple[Any, Any]]:
        """Compare existing and incoming records. Return changed fields.

        Returns:
            {field_name: (old_value, new_value)} for changed fields only.
        """
        changes: dict[str, tuple[Any, Any]] = {}

        for field in TRACKED_FIELDS:
            old_val = existing.get(field)
            new_val = incoming.get(field)

            # Skip if incoming is empty/None
            if new_val in (None, "", [], {}):
                continue

            # Skip if values are the same
            if self._values_equal(old_val, new_val):
                continue

            changes[field] = (old_val, new_val)

        return changes

    def is_significant_change(self, changes: dict[str, tuple[Any, Any]]) -> bool:
        """Check if changes include significant fields."""
        return bool(set(changes.keys()) & SIGNIFICANT_FIELDS)

    def _values_equal(self, a: Any, b: Any) -> bool:
        """Compare values, handling str/None normalization."""
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False

        # Normalize strings
        if isinstance(a, str) and isinstance(b, str):
            return a.strip().lower() == b.strip().lower()

        # Compare lists (order-insensitive for tags/sources)
        if isinstance(a, list) and isinstance(b, list):
            return sorted(str(x) for x in a) == sorted(str(x) for x in b)

        return a == b

    def build_change_summary(self, changes: dict[str, tuple[Any, Any]]) -> str:
        """Build human-readable summary of changes."""
        parts = []
        for field, (old, new) in changes.items():
            parts.append(f"{field}: {old!r} → {new!r}")
        return "; ".join(parts)
