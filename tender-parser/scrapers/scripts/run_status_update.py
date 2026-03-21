#!/usr/bin/env python3
"""Перенаправление на tender-parser/scripts/run_status_update.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_path = _ROOT / "scripts" / "run_status_update.py"
_spec = importlib.util.spec_from_file_location("run_status_update", _path)
if _spec is None or _spec.loader is None:
    print("Cannot load scripts/run_status_update.py", file=sys.stderr)
    raise SystemExit(1)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
raise SystemExit(_mod.main())
