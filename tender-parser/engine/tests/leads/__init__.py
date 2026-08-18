"""Тесты домена leads.

Лежат отдельно от ``tests/``, потому что существующий CI ставит только
``requirements.txt`` (без bs4, lxml и PyYAML) и гоняет ``pytest tests/``.
Домен leads требует парсерных зависимостей, поэтому у него свой workflow —
``.github/workflows/test-leads.yml``. Так добавление домена не может уронить
проверки tenders и funding.

Запуск локально:

    pytest engine/tests/leads/ -v
"""
