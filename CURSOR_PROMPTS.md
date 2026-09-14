# Промпт для Cursor AI — Доработка парсера тендеров

Скопируй нужный блок и вставь в Cursor (Cmd+K или чат).

---

## ПРОМПТ 1 — Расширение покрытия 223-ФЗ и коммерческих

```
Прочитай CLAUDE.md и всю структуру проекта. Нужно расширить покрытие тендеров.

ТЕКУЩАЯ ПРОБЛЕМА: 
- 44-ФЗ покрыт хорошо (ЕИС FTP + API + 3 ЭТП)
- 223-ФЗ покрыт слабо (только tektorg.py и частично eis_api.py)
- Коммерческие покрыты слабо (только b2b_center.py + tenderguru.py)

ЗАДАЧА — добавить парсеры:

### 223-ФЗ:
1. scrapers/zakupki_223.py — парсер раздела 223-ФЗ на zakupki.gov.ru
   - URL: https://zakupki.gov.ru/223/purchase/public/purchase/info/search.html
   - Поиск по ключевым словам, НМЦК, регион
   - law_type = "223-fz"

2. scrapers/etpgpb.py — ЭТП ГПБ (etpgpb.ru) 
   - Газпромбанк, крупные 223-ФЗ закупки
   - URL: https://etpgpb.ru/procedures/
   
3. scrapers/etp_ets.py — Национальная электронная площадка (etp-ets.ru)
   - URL: https://etp-ets.ru/

### Коммерческие:
4. scrapers/fabrikant.py — Fabrikant (fabrikant.ru)
   - URL: https://www.fabrikant.ru/trades/
   - Крупная коммерческая площадка

5. scrapers/tenderpro.py — TenderPro (tenderpro.ru)  
   - URL: https://www.tenderpro.ru/

6. scrapers/bicotender.py — Bicotender (bicotender.ru)
   - Агрегатор, хорошо парсится

### Строительные (для ниши "подряды"):
7. scrapers/synapsenet.py — SynapseNet (synapsenet.ru)
   - Агрегатор строительных тендеров

ТРЕБОВАНИЯ к каждому парсеру:
- Наследуй от BaseScraper (scrapers/base.py)
- Используй self.fetch(url) для HTTP
- min_delay = 3.0, max_delay = 7.0 (для госплощадок 4.0-8.0)
- Возвращай list[TenderCreate]
- Определяй law_type корректно: "44-fz", "223-fz", или "commercial"
- Обрабатывай пагинацию
- CSS-селекторы адаптируй под реальную вёрстку (используй несколько fallback-селекторов)

После создания парсеров:
1. Добавь их в scripts/run_parser.py в соответствующие группы
2. Создай .github/workflows/parse_223fz.yml (cron каждые 8 часов) для 223-ФЗ парсеров
3. Обнови CLAUDE.md списком парсеров
```

---

## ПРОМПТ 2 — Улучшение Telegram-бота

```
Прочитай bot/handler.py, bot/keyboards.py, bot/messages.py.

Доработай бота:

1. WIZARD ПОДПИСКИ — сейчас subscribe не полностью работает.
   Реализуй полный wizard через callback_data с состоянием:
   - callback_data формат: "sub_wiz:{step}:{data}" 
     Пример: "sub_wiz:region:furniture" → "sub_wiz:nmck:furniture:Омская область"
   - Шаги: ниша → регион → НМЦК → подтверждение → сохранение
   - На шаге подтверждения показать сводку: "Ниша: Мебель, Регион: Омская обл., НМЦК: до 5М"
   - При подтверждении — вызвать shared/db.py:add_subscription()

2. ТЕКСТОВЫЙ ПОИСК — сейчас любой текст идёт в поиск. Нужно:
   - После нажатия "🔎 Свой запрос" установить состояние ожидания текста
   - Хранить состояние в Supabase таблице bot_state (telegram_user_id, state, data JSONB)
   - Создай таблицу bot_state в scripts/init_db.sql
   - Если состояние = "awaiting_search_query" → текст = поисковый запрос
   - Если состояние = null → показать главное меню с подсказкой

3. КАРТОЧКА ТЕНДЕРА — добавь кнопку "📄 Документы" если documents_urls не пустой

4. КОМАНДА /stats — статистика для пользователя:
   - Всего тендеров в базе
   - Новых за сегодня
   - По нишам: мебель X шт, подряды Y шт
   
Все сообщения в HTML parse_mode. Используй httpx для Telegram API (не aiogram).
```

---

## ПРОМПТ 3 — Селекторы и тестирование парсеров

```
Проблема: CSS-селекторы в парсерах написаны "вслепую" — они могут не совпадать с реальной вёрсткой площадок.

Для каждого парсера в scrapers/:
1. Добавь метод test_connection() → bool:
   - Делает один запрос к площадке
   - Проверяет что страница доступна (HTTP 200)
   - Пробует найти хотя бы 1 тендер
   - Логирует результат
   
2. Добавь в каждый парсер НЕСКОЛЬКО fallback CSS-селекторов:
   - Основной селектор (текущий)
   - Fallback 1: более общий (например div[class*="tender"], div[class*="result"])
   - Fallback 2: по структуре (table tr, article, section > div)
   
3. Создай scripts/test_scrapers.py:
   - Запускает test_connection() для каждого парсера
   - Выводит таблицу: площадка | статус | найдено тендеров
   - Можно запустить: python scripts/test_scrapers.py

4. Создай .github/workflows/test_scrapers.yml:
   - Cron: раз в неделю (0 0 * * 0)
   - Запускает test_scrapers.py
   - Если парсер не работает — создаёт GitHub Issue автоматически
```

---

## ПРОМПТ 4 — Веб-интерфейс (Next.js)

```
Создай Next.js 14 фронтенд для Vercel.
Используй App Router, Tailwind CSS, shadcn/ui.
Данные берём из существующего API: GET /api/tenders

Страницы:
1. / — главная с поиском:
   - Поисковая строка
   - Фильтры: регион (select), НМЦК от-до, тип закона (44/223/коммерческий), ниша
   - Таблица результатов с пагинацией
   - Клик по строке → модальное окно с карточкой тендера

2. /dashboard — аналитика:
   - Карточки: всего тендеров, новых сегодня, средняя НМЦК
   - Графики: тендеры по дням (line chart), по регионам (bar), по нишам (pie)
   - Recharts для графиков

Стек: TypeScript, next 14, tailwindcss, shadcn/ui, recharts
Деплой: тот же Vercel проект (frontend/ директория или отдельный Vercel проект)
```

---

## ПРОМПТ 5 — Деплой и отладка

```
Помоги мне задеплоить проект:

1. Проверь что vercel.json корректен для Python runtime
2. Проверь что все импорты работают (sys.path.insert в api/*.py)
3. Убедись что requirements.txt содержит ВСЕ зависимости
4. Напиши скрипт scripts/test_local.py который:
   - Эмулирует Telegram webhook локально
   - Отправляет тестовый Update с командой /start
   - Проверяет что handler отрабатывает без ошибок
5. Добавь в README.md секцию "Troubleshooting" с частыми ошибками:
   - Vercel 500 → проверить env vars
   - Bot не отвечает → проверить webhook (getWebhookInfo)
   - Парсер падает → проверить доступность площадки
```
