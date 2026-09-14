# Архитектура: карта проекта и известные ограничения

Документ описывает **фактическое** состояние системы, а не желаемое. Он нужен
всем — людям и агентам, — кто собирается что-то здесь менять. Если код и этот
документ разошлись, чините документ вместе с кодом.

Дата последней сверки с продом: 2026-08-31.

---

## 1. Главное, что нужно знать до первой правки

**В проекте два параллельных, несвязанных стека парсинга.**

| | `scrapers/` (легаси) | `engine/` (новый) |
|---|---|---|
| Кто использует | `tenders`, `funding` — **весь прод** | только `leads/` |
| Реестр источников | нет | `engine/config/registry.py` |
| Пул прокси | нет | `engine/resilience/proxy_pool.py` |
| Circuit breaker | добавлен вручную в `base.py` | `engine/resilience/circuit_breaker.py` |
| robots.txt | не проверяется | `engine/fetchers/robots.py`, fail-closed |
| Rate limiter | `min_delay`/`max_delay` в классе | `engine/resilience/rate_limiter.py` |
| Абстракция хранилища | нет, прямой вызов `shared/db.py` | `engine/persistence/repository.py` |
| Наблюдаемость | `scrape_log` | `engine/observability/{health,metrics}.py` |

Проверить утверждение можно так — вне `engine/` и его тестов совпадения будут
только в `leads/*` и одном тесте:

```bash
grep -rl "from engine" --include=*.py . | grep -v "^./engine"
```

**Следствие.** Инфраструктура для «любого гео и любой ниши» уже наполовину
написана — она в `engine/`. Она просто не подключена к основному домену.
Расширять покрытие площадок стоит через достройку `engine/` и постепенную
миграцию на него `tenders`, а не через добавление новых классов в `scrapers/`.

---

## 2. Где что лежит

```
tender-parser/
  scrapers/          28 парсеров, наследуют BaseScraper / PlaywrightScraper /
                     FundingBaseScraper
  engine/
    config/registry.py        центральный реестр источников
    fetchers/                 http, browser, ftp, polite, robots
    resilience/               circuit_breaker, proxy_pool, rate_limiter, retry_policy
    persistence/              repository, supabase_repo
    observability/            health, metrics, logger
    parsers/                  html, json, xml, utils
    normalizers/              law_type, purchase_method, tender_normalizer
    pipeline/                 orchestrator, deduplicator, tagger, versioner
    sources/tenders/          eis_api, b2b_center, corporate
    sources/leads/            made_in_china, company_site, customs_api
  leads/             домен leads поверх engine/ (см. docs/LEADS.md)
  pipeline/          легаси-конвейер: normalizer → tagger → deduplicator → notifier
  shared/            config, db, models, constants, keyword_match, rate_limiter
  bot/  api/  web/   Telegram, Vercel-хендлеры, PWA-фронтенд
  scripts/           точки входа для Actions + SQL-миграции
  config/            leads_profiles.yaml, leads_blacklist.txt
```

Workflow лежат в `.github/workflows/` **в корне репозитория**, а не в
`tender-parser/`. GitHub читает только корень. Шаги выполняются в подкаталоге
через `defaults.run.working-directory: tender-parser`.

---

## 3. Блокирующее ограничение: сетевой доступ

**Крупнейшие тендерные площадки РФ не отвечают на TCP-соединение с раннеров
GitHub Actions.** `zakupki.gov.ru`, `sberbank-ast.ru` и другие дают
`ConnectTimeout`. При этом сайты грантов (`corpmsp.ru`, `frprf.ru`) с тех же
самых раннеров работают штатно.

Вывод: площадки закрыты для зарубежных IP, а раннеры GitHub находятся вне РФ.

**Это не чинится правкой селекторов или таймаутов.** Пока трафик идёт с
зарубежных адресов, эти площадки недоступны в принципе. Варианты решения: выделенная VM `parser-scraper` в Yandex Cloud (`ru-central1-a`, российский эгресс) — уже построена, см. `docs/INFRASTRUCTURE.md`. Антибот-площадки (`b2b-center`, `rts-tender`) дополнительно обходятся через прокси/ScrapingBee по решению владельца (`SCRAPING_POLICY.md` §2).

---

## 4. Состояние площадок

Выборка из `scrape_log` за двое суток, 2026-08-31. Цифры живые, пересними
перед тем, как на них опираться:

```sql
SELECT scraper_name, count(*) AS runs,
       sum(coalesce(tenders_found, 0))    AS found,
       sum(coalesce(tenders_inserted, 0)) AS inserted,
       round(avg(duration_ms)/1000.0)     AS avg_sec,
       max(started_at)                    AS last_run
FROM scrape_log
WHERE started_at > now() - interval '2 days'
GROUP BY scraper_name ORDER BY found DESC;
```

**Сохраняют данные:**

| Источник | Найдено за 2 суток | Среднее время |
|---|---|---|
| `lot_online` (РАД, банкротные торги) | 929 | ~10 мин |
| `mybusiness` (гранты) | 42 | 19 с |
| `frprf` (гранты) | 35 | 21 с |
| `mspbank` (гранты) | 28 | 43 с |
| `corpmsp` (гранты) | 28 | 20 с |

**Отрабатывают со статусом `success`, но возвращают ноль:**
`eis_ftp`, `eis_api`, `eis_api_extra`, `roseltorg`, `sberbank_ast`,
`rts_tender`, `tektorg`, `b2b_center`, `tenderguru`, `torgi_gov_pw`,
`tektorg_pw`, `fabrikant_pw`. Причина — §3, а не поломка парсеров.

**Особый случай — `rostender`.** Площадка живая: отдаёт `HTTP 200` и по 20
тендеров со страницы. Но в `scrape_log` у неё всегда `status='running'` и
`completed_at IS NULL` — job убивали по таймауту до сохранения. Бюджет прохода:
35 поисковых запросов × 5 страниц × ~5.5 с задержки ≈ 16 минут, а доставалось
ей ~7 минут из общих 25. Разложено на параллельную матрицу заданий по 30 минут
(PR #10, 2026-08-31); на момент написания первый прогон на новой схеме ещё не
отработал — проверьте результат.

**Исторический факт для калибровки ожиданий:** все 30 последних плановых
прогонов `Parse Tenders` до PR #10 завершились с `conclusion: cancelled`.
Не «иногда не успевал» — не успевал всегда.

---

## 5. Ловушка, из-за которой здесь легко ошибиться

**В этом проекте отказ выглядит как успех.**

- Парсер, вернувший ноль тендеров, пишет в `scrape_log` `status='success'`.
- `_run_with_log` гасит исключение отдельного источника в лог и идёт дальше —
  прогон в целом остаётся зелёным.
- Smoke-тест когда-то печатал `PASS: Scrape log` при полностью недоступной
  базе, потому что `get_scrape_health()` глушит исключение внутри и возвращает
  пустой список. Починено, но сам класс ошибки характерен для кодовой базы.
- Незавершённая запись выглядит как `status='running'` навсегда —
  `completed_at IS NULL` значит, что job убили, а не что парсер работает.

**Правило: нулевой результат считается подозрительным, пока не доказано
обратное.** Зелёный workflow — не доказательство того, что данные собраны.
Доказательство — ненулевой `tenders_inserted` в `scrape_log`.

---

## 6. Известные грабли — все уже случались

1. **Workflow в подкаталоге.** `.github/` переехал в `tender-parser/` (коммит
   `ffcc846`, 2026-05-06) — Actions не запускался 3 месяца, никто не заметил.
2. **`run`-шаг до `checkout`** при заданном `working-directory` падает с
   `No such file or directory`. `uses`-шаги этому параметру не подчиняются.
3. **Рассинхрон имени секрета.** Workflow ждал `SUPABASE_SERVICE_ROLE_KEY`, в
   репозитории лежал `SUPABASE_KEY` → `supabase_key is required` во всех
   прогонах. Теперь ключ пробрасывается под тремя именами, а
   `shared/config.supabase_key()` берёт первое непустое. Это сделано намеренно.
4. **Тегирование по подстроке.** «молочных продуктов» → тег `medical` (нашлось
   «КТ»), «в случае аварии» → `it` (нашлось «ИИ»), «спортивного зала» →
   `transport` (нашлось «порт»). Мусорные теги управляли рассылкой подписчикам.
   Починено границами слов в `shared/keyword_match.py` — не откатывайте.
5. **`playwright` не был ни в одном requirements**, хотя от него зависели 4
   парсера. Молча возвращали ноль. Вынесен в `requirements-playwright.txt`.
6. **Нотификатор без потолка на прогон.** Первый прогон после паузы разослал бы
   подписчику по сообщению на каждый тендер из бэклога. Введён
   `MAX_NOTIFICATIONS_PER_SUBSCRIPTION` (по умолчанию 10).
7. **Мёртвый хост съедал весь бюджет времени** последовательного прогона, живым
   источникам не доставалось. Починено предохранителем `HostUnreachable` в
   `scrapers/base.py` плюс параллельной матрицей заданий.
8. **Общий таймаут расходовался на установку соединения.** Живой сайт отвечает
   на рукопожатие за доли секунды; 30 секунд осмысленны для медленного ответа,
   а не для подключения. Введён отдельный `connect_timeout = 8`.

---

## 7. Ограничения, которые нельзя нарушать

- Домены `tenders` и `funding` работают в проде. Любая миграция — за
  фиче-флагом, с возможностью отката.
- Миграции БД только аддитивные и идемпотентные. Образец —
  `scripts/migration_leads.sql`.
- Новый домен добавляется рядом, за своим фиче-флагом, выключенным по
  умолчанию, со своей точкой входа и своим расписанием — не в общем цикле с
  тендерами.
- Правила вежливого скрапинга — `docs/SCRAPING_POLICY.md`. Они обязательны для
  всех доменов, а не только для `leads`.
