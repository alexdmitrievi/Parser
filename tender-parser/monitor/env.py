"""Загрузка .env без внешних зависимостей.

systemd загружает окружение через EnvironmentFile, но при ручном запуске
(python -m monitor.run_cycle) удобно подхватить .env из корня проекта.
Уже установленные переменные окружения имеют приоритет.
"""

from __future__ import annotations

import os


def load_dotenv(path: str | None = None) -> None:
    if path is None:
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
        )
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
