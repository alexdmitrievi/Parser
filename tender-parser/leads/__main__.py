"""Запуск домена leads: ``python -m leads <команда>``."""

from __future__ import annotations

import sys
from pathlib import Path

# Позволяет запускать из корня проекта без установки пакета.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from leads.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
