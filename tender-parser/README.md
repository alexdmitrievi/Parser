# Парсер Тендеров — Telegram Bot + API

Система парсинга тендеров с государственных и коммерческих площадок РФ.
Telegram-бот с поиском, фильтрами и автоматическими уведомлениями.

## Локальный запуск API и веб-страниц

Рабочая директория — **`tender-parser`** (каталог с `api/`, `web/`, `requirements-parser.txt`).

```bash
cd tender-parser
python -m pip install -r requirements-parser.txt
copy .env.example .env
# заполните .env (TELEGRAM_BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY)
```

Запуск FastAPI с автоперезагрузкой:

```bash
npm run dev
```

То же самое без npm:

```bash
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Открыть в браузере: [http://127.0.0.1:8000/web/](http://127.0.0.1:8000/web/) (поиск), [http://127.0.0.1:8000/web/subscribe.html](http://127.0.0.1:8000/web/subscribe.html) (подписки), документация API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Архитектура

| Компонент | Сервис | Стоимость |
|-----------|--------|-----------|
| Telegram бот (webhook) | Vercel Serverless | Бесплатно |
| API поиска | Vercel Serverless | Бесплатно |
| Парсинг (cron) | GitHub Actions | Бесплатно |
| Уведомления (cron) | GitHub Actions | Бесплатно |
| База данных | Supabase PostgreSQL | Бесплатно (500MB) |

## Деплой: пошаговая инструкция

### Шаг 1: Создать Telegram-бота
1. Открыть @BotFather в Telegram
2. Отправить /newbot, задать имя и username
3. Скопировать токен

### Шаг 2: Создать БД в Supabase
1. Зайти на supabase.com, создать проект
2. SQL Editor → выполнить scripts/init_db.sql
3. Settings → API → скопировать URL и anon key

### Шаг 3: Запушить в GitHub
```bash
cd tender-parser
git init && git add . && git commit -m "init"
git branch -M main
git remote add origin https://github.com/YOU/tender-parser.git
git push -u origin main
```
Settings → Secrets → добавить: TELEGRAM_BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY

### Шаг 4: Деплой на Vercel
1. vercel.com → Add New Project → выбрать репо
2. Environment Variables → добавить те же 3 переменные
3. Deploy

### Шаг 5: Установить Webhook
```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<VERCEL_URL>/api/webhook
```

### Шаг 6: Проверить
Написать боту /start в Telegram.

## Команды бота
- /start — Главное меню
- /search — Поиск тендеров
- /subscribe — Создать подписку
- /mysubs — Мои подписки
- /hot — Горячие тендеры
- /help — Справка

## API
```
GET /api/tenders?q=мебель&region=Москва&niche=furniture&page=1
```

## Ниши
- Мебель (ОКПД2: 31.0x) — Омск, Новосибирск, Тюмень
- Подряды (ОКПД2: 41-43, 71.1, 81.1) — вся РФ
