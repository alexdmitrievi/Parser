"""
Vercel serverless: ASGI через Mangum (тот же FastAPI, что и api.main).
Корневой каталог репозитория должен быть в PYTHONPATH — см. sys.path ниже.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mangum import Mangum

from api.main import app

handler = Mangum(app, lifespan="off")
