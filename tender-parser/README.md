# 🔍 Парсер Тендеров — Telegram Bot + API

Система парсинга тендеров с государственных и коммерческих площадок РФ.
Telegram-бот для поиска и подписки на тендеры. Бесплатный хостинг.

## Архитектура

```
GitHub Actions (cron)  →  Парсинг площадок  →  Supabase (PostgreSQL)
                                                       ↑
Vercel (serverless)    →  Telegram webhook   →  Поиск / подписки
                       →  REST API /api/tenders
```

## Площадки

- **ЕИС** (zakupki.gov.ru) — FTP-выгрузки, 44-ФЗ, 223-ФЗ
- **TenderGuru** — агрегатор (HTTP scraping)
- *Планируется:* Сбербанк-АСТ, РТС-тендер, B2B-Center, Fabrikant

## Ниши (пресеты)

- 🛋 **Мебель** — ОКПД2: 31.x, ключевые слова: мебель, диван, кресло...
- 🏗 **Подряды** — ОКПД2: 41-43, 71.1, ключевые слова: подряд, ремонт, СМР...

---

## Быстрый старт (15 минут)

### 1. Создать Telegram-бота

1. Открой [@BotFather](https://t.me/BotFather)
2. `/newbot` → задай имя и username
3. Скопируй токен (формат: `123456:ABC-DEF...`)

### 2. Создать базу данных в Supabase

1. Зайди на [supabase.com](https://supabase.com), создай проект
2. Открой **SQL Editor**
3. Скопируй содержимое `scripts/init_db.sql` и выполни
4. Запиши **Project URL** и **anon key** из Settings → API

### 3. Форкнуть репозиторий и добавить секреты

1. Форкни этот репозиторий на GitHub
2. Перейди в Settings → Secrets and variables → Actions
3. Добавь секреты:
   - `TELEGRAM_BOT_TOKEN` — токен бота
   - `SUPABASE_URL` — URL проекта (https://xxxxx.supabase.co)
   - `SUPABASE_KEY` — anon key

### 4. Деплой на Vercel

1. Зайди на [vercel.com](https://vercel.com), подключи GitHub-репо
2. В настройках проекта добавь Environment Variables:
   - `TELEGRAM_BOT_TOKEN`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
3. Деплой произойдёт автоматически

### 5. Установить Telegram webhook

```bash
# Замени URL на свой Vercel-домен
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export SUPABASE_URL="https://xxxxx.supabase.co"
export SUPABASE_KEY="eyJhb..."

python scripts/setup_webhook.py https://YOUR-PROJECT.vercel.app/api/webhook
```

Или вручную в браузере:
```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://YOUR-PROJECT.vercel.app/api/webhook
```

### 6. Готово!

- GitHub Actions запустятся автоматически по cron (парсинг + рассылка)
- Для ручного запуска: Actions → Parse EIS FTP → Run workflow
- Откройте бота в Telegram и нажмите `/start`

---

## Структура проекта

```
tender-parser/
├── api/                    # Vercel Serverless Functions
│   ├── webhook.py          # POST /api/webhook — Telegram
│   └── tenders.py          # GET /api/tenders — REST API
├── bot/                    # Telegram-бот
│   ├── handler.py          # Роутинг команд и callback
│   ├── keyboards.py        # Inline-клавиатуры
│   └── messages.py         # Шаблоны сообщений
├── scrapers/               # Парсеры площадок
│   ├── base.py             # Базовый класс
│   ├── eis_ftp.py          # ЕИС FTP
│   └── tenderguru.py       # TenderGuru
├── pipeline/               # Обработка данных
│   ├── normalizer.py       # Нормализация
│   ├── tagger.py           # Авто-тегирование по нишам
│   └── notifier.py         # Рассылка уведомлений
├── shared/                 # Общие модули
│   ├── config.py           # Конфигурация
│   ├── db.py               # Supabase клиент
│   ├── models.py           # Pydantic-модели
│   └── constants.py        # Константы
├── scripts/
│   ├── run_parser.py       # Запуск парсеров
│   ├── run_notifier.py     # Запуск рассылки
│   ├── setup_webhook.py    # Установка webhook
│   └── init_db.sql         # SQL миграция
├── .github/workflows/      # GitHub Actions cron
├── vercel.json
├── requirements.txt
└── .env.example
```

## API

```
GET /api/tenders?q=мебель&region=Омская+область&min_nmck=100000&page=1
```

Параметры: `q`, `region`, `min_nmck`, `max_nmck`, `okpd2`, `niche`, `status`, `law_type`, `page`, `per_page`

## Добавление новых площадок

1. Создай файл `scrapers/new_platform.py`
2. Наследуй от `BaseScraper`
3. Реализуй `parse_tenders()` и `run()`
4. Добавь вызов в `scripts/run_parser.py`
5. Добавь GitHub Actions workflow

---

**Лицензия:** MIT
