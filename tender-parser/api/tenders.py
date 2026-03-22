"""
Vercel serverless: ASGI через Mangum (тот же FastAPI, что и api.main).
Корневой каталог репозитория должен быть в PYTHONPATH — см. sys.path ниже.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

# Добавить корень проекта в sys.path для импорта shared/, bot/, pipeline/
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from mangum import Mangum
    from api.main import app

    handler = Mangum(app, lifespan="off")
except Exception:
    # Если импорт не удался — вернуть ошибку в виде валидного HTTP-ответа
    _err = traceback.format_exc()

    def handler(event, context):
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Import failed", "detail": _err}),
        }
