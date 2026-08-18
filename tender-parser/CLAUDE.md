# Тендер PRO — Инструкции для AI

## Обзор проекта

Система парсинга тендеров РФ (44-ФЗ, 223-ФЗ, коммерческие, банкротство, гранты МСП) с Telegram-ботом и веб-интерфейсом. Бесплатный хостинг: Vercel (веб + бот webhook) + GitHub Actions (cron-парсинг) + Supabase (БД).

## Стек

- Python 3.12+, httpx, BeautifulSoup4, lxml, pydantic
- Supabase (PostgreSQL) через supabase-py
- Vercel Serverless Functions (Python runtime, BaseHTTPRequestHandler)
- GitHub Actions (cron-парсинг)
- Telegram Bot API: **python-telegram-bot используется в bot/handler.py** для локальной разработки и Vercel webhook
- Frontend: Vanilla JS (PWA с Service Worker), Chart.js на странице аналитики

## Архитектура

```
leads/              → домен leads: CLI, профили, почты, дедуп, экспорт, хранилище (см. docs/LEADS.md)
engine/sources/leads/ → адаптеры leads: каталоги, сайты компаний, таможенные данные
scrapers/           → парсеры площадок (наследуют BaseScraper / PlaywrightScraper / FundingBaseScraper)
pipeline/           → normalizer → tagger → deduplicator → notifier
bot/                → Telegram handler (webhook + polling), messages (format_tender_card)
api/
  ├── main.py       → FastAPI приложение (только для локальной разработки: npm run dev)
  ├── tenders.py    → Vercel serverless handler (НЕ использует FastAPI — прямые вызовы shared/)
  ├── webhook.py    → Telegram webhook handler (Vercel)
  ├── debug.py      → Диагностика (Vercel)
  └── routes_*.py   → Роутеры FastAPI (локальный dev)
shared/             → config, db, models, constants, rate_limiter, logging_config, time_utils
scripts/            → entry points для GitHub Actions + миграции + build_frontend.py
web/                → Статический фронтенд (PWA)
tests/              → Unit + интеграционные тесты
(корень репо)/.github/workflows/ → 10 workflow: parse (tenders/auctions/funding/leads),
                    notify, backup, smoke-test, status-update, test.
                    Лежат в КОРНЕ репозитория (GitHub читает только оттуда),
                    а шаги выполняются в tender-parser через
                    defaults.run.working-directory
```

## Ключевые изменения (v4)

1. **Vercel handler без FastAPI** — `api/tenders.py` написан на чистом `BaseHTTPRequestHandler`, без Starlette/TestClient. Cold start с 3-7 сек до < 1 сек.
2. **FTS полнотекстовый поиск** — `shared/db.py` использует `text_search("fts", query)` через GIN-индекс вместо медленного `ilike('%word%')`.
3. **DB-агрегация** — `/api/stats`, `/api/meta`, `/api/funding/meta` используют PostgreSQL RPC-функции (`get_tender_stats()`, `get_tender_meta()`, `get_funding_meta()`) вместо загрузки 5000 строк в Python.
4. **Фронтенд-бандлинг** — `scripts/build_frontend.py` конкатенирует JS в правильном порядке (shared.js → navbar.js → page.js), минифицирует CSS.
5. **RLS включён** — Row Level Security на всех таблицах для production.
6. **scrape_log** — Таблица для мониторинга здоровья парсеров.
7. **Тесты** — 64 unit-тестов (models, deduplication, notifier matching, config), CI-запуск через GitHub Actions.

## Стиль кода

- Type hints везде
- Docstrings: Google style
- Logging: структурированный JSON (по умолчанию), отключается через `LOG_FORMAT=text`
- Обработка ошибок: try/except с логированием, graceful degradation
- Формат: совместимо с ruff (`ruff check . --ignore E501`)

## Ограничения Vercel

- Vercel Python runtime использует BaseHTTPRequestHandler (НЕ Flask, НЕ FastAPI)
- Макс 10 секунд execution на Hobby
- НЕ поддерживает async (используется `_run_async` с event loop)
- Каждый файл в api/ — отдельная serverless function
- **api/tenders.py обрабатывает ВСЕ API-запросы** кроме webhook и debug

## Команды

```bash
npm run dev      # Локальный FastAPI сервер (http://localhost:8000)
npm run build    # Сборка фронтенда (bundle JS + minify CSS)
npm test         # Запуск тестов
npm run lint     # Проверка кода (ruff)
```

### Домен leads (китайские импортёры)

Закрыт фиче-флагом `LEADS_ENABLED` (по умолчанию `false`) — при выключенном
флаге поведение проекта не меняется. Отдельная точка входа и отдельное
расписание, не в общем цикле с тендерами.

```bash
python -m leads collect --profile petcoke_anode   # сбор из каталогов
python -m leads enrich                            # обход сайтов, сбор почт
python -m leads export --profile petcoke_anode --out leads.csv
python -m leads stats
pytest engine/tests/leads/ -v                     # тесты домена
```

Правила домена (подробно — `docs/LEADS.md`): соблюдается `robots.txt`,
задержка не меньше конфига, конкурентность не выше 2, честный User-Agent с
контактом, антибот-защита не обходится, по PIPL в экспорт идут только ролевые
адреса. Прокси и ротация User-Agent в этом домене запрещены — используется
`PoliteFetcher`, а не `HttpFetcher`.

## Парсеры — правила

Каждый парсер:
1. Наследует от `scrapers/base.py:BaseScraper`
2. Реализует `parse_tenders()` и `run()`
3. Использует `self.fetch(url)` для HTTP (встроенный retry + rate limit)
4. Возвращает `list[TenderCreate]`
5. min_delay/max_delay — обязательная задержка между запросами

## Модель данных

### TenderCreate
Обязательные: `source_platform`, `title`
Важные: `registry_number`, `law_type` (44-fz/223-fz/commercial), `nmck`, `customer_name`, `customer_region`, `submission_deadline`, `original_url`

### SubscriptionCreate
Обязательные: `telegram_user_id`, `name`

### FundingProgramCreate
Обязательные: `source_platform`, `program_name`, `program_type`, `original_url`

## Ниши

- furniture (мебель): ОКПД2 31.x
- construction (подряды): ОКПД2 41-43, 71.1, 81.1

## API Endpoints (Vercel)

```
GET  /api/search/tenders        — полнотекстовый поиск (FTS)
GET  /api/tenders               — список с фильтрами
GET  /api/tenders/{id}          — один тендер
GET  /api/stats                 — агрегированная статистика (RPC)
GET  /api/meta                  — enrichment: niches, platforms, methods (RPC)
GET  /api/niches                — список ниш
GET  /api/suggest/regions       — автодополнение регионов
GET  /api/suggest/customers     — автодополнение заказчиков
GET  /api/suggest/platforms     — список площадок
GET  /api/suggest/purchase-methods — способы закупок
GET  /api/funding               — программы финансирования
GET  /api/funding/meta          — мета-информация (RPC)
GET  /api/funding/{id}          — одна программа
POST /api/subscriptions/create  — создать подписку
GET  /api/subscriptions/list    — список подписок
DELETE /api/subscriptions/{id}  — удалить подписку
GET  /health                    — health-check
GET  /api/health/full           — расширенный мониторинг
```

## Таблицы БД

- `tenders` — тендеры (с FTS индексом)
- `subscriptions` — подписки
- `notifications_log` — лог уведомлений
- `bot_users` — пользователи бота
- `bot_state` — состояние диалогов
- `funding_programs` — программы финансирования МСП
- `scrape_log` — мониторинг парсеров
- `rate_limits` — DB-based rate limiting
- `leads_companies`, `leads_emails`, `leads_runs` — домен leads (только при `LEADS_STORAGE=supabase`)

## Миграции

- `scripts/init_db.sql` — первоначальная схема
- `scripts/migration_v2.sql` — v2 изменения
- `scripts/migration_v3_production.sql` — v3 изменения
- `scripts/migration_v4.sql` — RPC функции + RLS + scrape_log + rate_limits + обновлённый FTS
- `scripts/migration_leads.sql` — таблицы домена leads (идемпотентна, нужна только при `LEADS_STORAGE=supabase`)
