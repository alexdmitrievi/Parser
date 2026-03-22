# Привязка домена с рег.ру к Vercel

Пошаговая инструкция по привязке домена, купленного на reg.ru, к проекту на Vercel.

## Предварительные требования

- Аккаунт на [Vercel](https://vercel.com)
- Домен, купленный на [reg.ru](https://reg.ru)
- Проект развёрнут на Vercel (через GitHub интеграцию)

---

## Шаг 1. Развернуть проект на Vercel

1. Войти в [Vercel Dashboard](https://vercel.com/dashboard)
2. Нажать **Add New → Project**
3. Импортировать репозиторий из GitHub
4. Vercel автоматически определит `vercel.json` и настроит билд
5. В разделе **Settings → Environment Variables** добавить переменные:

| Переменная | Значение | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `123456:ABC...` | Токен бота от @BotFather |
| `SUPABASE_URL` | `https://xxx.supabase.co` | URL проекта Supabase |
| `SUPABASE_KEY` | `eyJ...` | Anon/public ключ Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJ...` | Service role ключ (для GitHub Actions) |
| `CORS_ORIGINS` | `https://yourdomain.ru` | Разрешённые домены для CORS |

6. Нажать **Deploy**

---

## Шаг 2. Добавить домен в Vercel

1. В Vercel Dashboard → ваш проект → **Settings → Domains**
2. Ввести ваш домен (например, `tenders.yourdomain.ru` или `yourdomain.ru`)
3. Нажать **Add**
4. Vercel покажет DNS-записи, которые нужно добавить (см. шаг 3)

---

## Шаг 3. Настроить DNS в панели рег.ру

1. Войти в [Личный кабинет reg.ru](https://www.reg.ru/user/account)
2. Перейти в **Мои домены** → выбрать домен
3. Перейти в **DNS-серверы и управление зоной** → **Изменить**
4. Убедиться, что используются DNS-серверы reg.ru (по умолчанию)
5. Перейти в **Управление зоной DNS** → **Добавить запись**

### Для корневого домена (`yourdomain.ru`):

| Тип записи | Хост | Значение |
|---|---|---|
| **A** | `@` | `76.76.21.21` |

### Для поддомена `www`:

| Тип записи | Хост | Значение |
|---|---|---|
| **CNAME** | `www` | `cname.vercel-dns.com` |

### Для поддомена (например, `tenders.yourdomain.ru`):

| Тип записи | Хост | Значение |
|---|---|---|
| **CNAME** | `tenders` | `cname.vercel-dns.com` |

6. Сохранить изменения

---

## Шаг 4. Дождаться пропагации DNS

- Обычно занимает от 5 минут до 48 часов
- Проверить можно командой:
  ```bash
  nslookup yourdomain.ru
  # Должен вернуть 76.76.21.21
  ```
- Или через [dnschecker.org](https://dnschecker.org)

---

## Шаг 5. SSL-сертификат

- Vercel **автоматически** выпустит бесплатный SSL-сертификат (Let's Encrypt)
- После пропагации DNS сайт будет доступен по `https://yourdomain.ru`
- Если SSL не появился в течение часа после пропагации DNS — проверить статус в Vercel Dashboard → Settings → Domains

---

## Шаг 6. Настроить Telegram Webhook

После привязки домена обновить webhook URL бота:

```bash
curl -X POST "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://yourdomain.ru/api/webhook"}'
```

Проверить webhook:
```bash
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo"
```

---

## Шаг 7. Обновить CORS_ORIGINS

В Vercel Dashboard → Settings → Environment Variables:
- Установить `CORS_ORIGINS` = `https://yourdomain.ru,https://www.yourdomain.ru`
- Переразвернуть проект (Deployments → Redeploy)

---

## Проверка

1. Открыть `https://yourdomain.ru/health` — должен вернуть `{"status": "ok"}`
2. Открыть `https://yourdomain.ru/web/` — страница поиска тендеров
3. Открыть `https://yourdomain.ru/web/subscribe.html` — страница подписок
4. Отправить `/start` боту в Telegram — бот должен ответить

---

## Возможные проблемы

| Проблема | Решение |
|---|---|
| SSL не выпускается | Проверить, что DNS-записи корректны и пропагировались |
| 404 на `/web/` | Проверить `vercel.json` — маршруты должны указывать на `api/tenders.py` |
| Бот не отвечает | Проверить webhook URL и переменную `TELEGRAM_BOT_TOKEN` |
| CORS ошибки | Добавить домен в `CORS_ORIGINS` и переразвернуть |
