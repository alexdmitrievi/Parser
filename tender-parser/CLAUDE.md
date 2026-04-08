# Парсер Тендеров — Инструкции для AI

## Обзор проекта

Система парсинга тендеров РФ (44-ФЗ, 223-ФЗ, коммерческие) с Telegram-ботом.
Бесплатный хостинг: Vercel (бот) + GitHub Actions (парсинг) + Supabase (БД).

## Стек

- Python 3.11+, httpx, BeautifulSoup4, lxml, pydantic
- Supabase (PostgreSQL) через supabase-py
- Vercel Serverless Functions (Python runtime, BaseHTTPRequestHandler)
- GitHub Actions (cron-парсинг)
- Telegram Bot API напрямую через httpx (НЕ aiogram, НЕ python-telegram-bot)

## Архитектура

```
scrapers/       → парсеры площадок (наследуют BaseScraper)
pipeline/       → normalizer → tagger → notifier
bot/            → Telegram webhook handler + keyboards + messages
api/            → Vercel serverless: webhook.py, tenders.py
shared/         → config, db, models, constants
scripts/        → entry points для GitHub Actions
.github/workflows/ → cron jobs
```

## Стиль кода

- Type hints ВЕЗДЕ
- Docstrings: Google style
- Logging: стандартный logging (не print)
- Обработка ошибок: try/except с логированием, graceful degradation
- Комментарии: бизнес-логика на русском, технические на английском
- Формат: совместимо с ruff

## Ограничения Vercel

- Vercel Python runtime использует BaseHTTPRequestHandler (НЕ Flask, НЕ FastAPI)
- Макс 10 секунд execution на Hobby
- НЕ поддерживает async
- Каждый файл в api/ — отдельная serverless function

## Парсеры — правила

Каждый парсер:
1. Наследует от `scrapers/base.py:BaseScraper`
2. Реализует `parse_tenders()` и `run()`
3. Использует `self.fetch(url)` для HTTP (встроенный retry + rate limit)
4. Возвращает `list[TenderCreate]`
5. min_delay/max_delay — обязательная задержка между запросами

## Модель данных (TenderCreate)

Обязательные поля: source_platform, title
Важные поля: registry_number, law_type (44-fz/223-fz/commercial), nmck, 
             customer_name, customer_region, submission_deadline, original_url

## Ниши

- furniture (мебель): ОКПД2 31.x, ключевые слова в shared/config.py
- construction (подряды): ОКПД2 41-43, 71.1, 81.1

## Текущие парсеры тендеров

- eis_ftp.py — FTP zakupki.gov.ru (44-ФЗ, XML)
- eis_api.py — HTTP поиск zakupki.gov.ru (44-ФЗ + 223-ФЗ)
- roseltorg.py — ЭТП Росэлторг (44-ФЗ)
- sberbank_ast.py — ЭТП Сбербанк-АСТ (44-ФЗ)
- rts_tender.py — ЭТП РТС-тендер (44-ФЗ)
- tektorg.py — ЭТП ТЭК-Торг (223-ФЗ)
- b2b_center.py — Коммерческие тендеры
- tenderguru.py — Агрегатор

## Парсеры программ финансирования МСП

Таблица: `funding_programs` в Supabase.
Базовый класс: `scrapers/funding_base.py:FundingBaseScraper`
Entry point: `scrapers/scripts/run_funding.py`

- funding_corpmsp.py — Корпорация МСП (corpmsp.ru): кредиты 1764, гарантии, микрозаймы, лизинг
- funding_frprf.py — Фонд развития промышленности (frprf.ru): займы 1-5% для производства
- funding_mspbank.py — МСП Банк (mspbank.ru): инвестиционные кредиты, гарантии, экспорт
- funding_mybusiness.py — Мой Бизнес (mybusiness.ru): гранты старт, социалка, субсидии

## Модель FundingProgramCreate

Обязательные поля: source_platform, program_name, program_type, original_url
Типы (program_type): grant, loan, microloan, subsidy, guarantee, compensation, leasing
API: GET /api/funding, GET /api/funding/{id}, GET /api/funding/meta
Фронтенд: /web/grants.html + /web/grants.js
