# Домен `leads` — китайские компании-импортёры

Сбор компаний-импортёров и потребителей в Китае с их сайтами и контактными
почтами для холодных B2B-рассылок (нефтяной кокс, зерно).

Домен полностью изолирован от `tenders` и `funding`: свои таблицы, своя точка
входа, своё расписание, свой фиче-флаг. При `LEADS_ENABLED=false` (значение по
умолчанию) поведение проекта не отличается от версии без этого модуля.

---

## Быстрый старт

```bash
pip install -r requirements-parser.txt

# 1. Включить домен и указать РАБОЧУЮ контактную почту
echo "LEADS_ENABLED=true" >> .env
echo "LEADS_CONTACT_EMAIL=ваш-ящик@вашдомен.ru" >> .env

# 2. Собрать компании из каталогов
python -m leads collect --profile petcoke_anode

# 3. Обойти их сайты и добрать почты
python -m leads enrich

# 4. Выгрузить CSV под Coldy
python -m leads export --profile petcoke_anode --out leads.csv

# 5. Посмотреть, что получилось
python -m leads stats
```

`LEADS_CONTACT_EMAIL` — не формальность. Краулер представляется этим адресом в
`User-Agent`, чтобы владелец сайта мог написать и попросить его не трогать.
Оставлять значение по умолчанию нельзя.

---

## Как включить

| Переменная | По умолчанию | Зачем |
|---|---|---|
| `LEADS_ENABLED` | `false` | Главный выключатель. При `false` CLI, бот и расписание не делают ничего |
| `LEADS_CONTACT_EMAIL` | `parser-abuse@example.com` | **Заменить обязательно.** Контакт в `User-Agent` |
| `LEADS_STORAGE` | `sqlite` | `sqlite` (локальный файл) или `supabase` |
| `LEADS_DB_PATH` | `data/leads.sqlite3` | Путь к базе при `LEADS_STORAGE=sqlite` |
| `LEADS_PROFILES_PATH` | `config/leads_profiles.yaml` | Профили продуктов |
| `LEADS_BLACKLIST_PATH` | `config/leads_blacklist.txt` | Список исключений |
| `LEADS_SOURCES` | пусто (все) | Список адаптеров через запятую |
| `LEADS_USER_AGENT` | собирается из контакта | Полное переопределение `User-Agent` |
| `LEADS_CUSTOMS_API_KEY` | пусто | Ключ платной таможенной подписки |
| `LEADS_CUSTOMS_API_PROVIDER` | `volza` | `volza` / `importgenius` / `panjiva` |
| `LEADS_CUSTOMS_API_BASE_URL` | пусто | Эндпоинт вашей подписки |
| `FIRECRAWL_API_KEY` | пусто | Ключ Firecrawl для Cloudflare-защищённых источников (all.biz) |
| `LEADS_FIRECRAWL_SOURCES` | пусто (никто) | Источники через Firecrawl, через запятую (обычно `allbiz`) |

Что именно даёт выключенный флаг:

* `python -m leads <любая команда>` печатает подсказку и выходит с кодом **0**
  (не 1 — чтобы выключенный домен не красил расписание в красный);
* база не создаётся, ни один файл не трогается;
* команда `/leads_stats` в боте **не регистрируется** — набор команд прежний;
* workflow `parse-leads.yml` отрабатывает вхолостую за секунды.

---

## Хранилище

По умолчанию — локальный SQLite. Так `collect`, `enrich`, `export`, `stats` и
тесты работают без облачных ключей. Схема создаётся сама при первом запуске,
миграция идемпотентна.

Чтобы писать в общий Supabase:

```bash
# 1. Применить миграцию в Supabase SQL Editor (можно повторно — она идемпотентна)
cat scripts/migration_leads.sql

# 2. Переключить хранилище
LEADS_STORAGE=supabase
```

Таблицы: `leads_companies`, `leads_emails`, `leads_runs`. Префикс `leads_`
гарантирует, что домен не пересекается с `tenders`, `funding_programs` и
остальными.

---

## Профили продуктов

Профили живут в `config/leads_profiles.yaml` и **перечитываются на каждом
запуске** — новый продукт добавляется правкой конфига, без изменения кода.

```yaml
profiles:
  petcoke_anode:
    keywords_en: ["calcined petroleum coke", "CPC", "anode grade coke"]
    keywords_zh: ["煅烧石油焦", "预焙阳极", "碳素"]
    hs_codes: ["2713.12"]                       # для customs_api
    target_industries: ["aluminium", "carbon"]  # для industry_guess

regions_priority: ["Shandong", "Hebei", "Henan", ...]   # порядок в экспорте

limits:
  max_pages_per_query: 20
  request_delay_seconds: 3      # не может быть меньше 1
  max_concurrency: 2            # не может быть больше 2
```

Нижние границы вежливого режима зашиты в коде и конфигом не ослабляются:
задержка меньше 1 секунды поднимается до 1, конкурентность выше 2 снижается
до 2, и в лог пишется предупреждение.

Готовые профили: `petcoke_fuel` (топливный кокс, сера ~4%), `petcoke_anode`
(электродный/кальцинация, сера ~1.5%), `grain` (пшеница, ячмень, рапс).

---

## Команды

```bash
# Сбор из каталогов
python -m leads collect --profile petcoke_anode
python -m leads collect --profile grain --source made_in_china   # один адаптер
python -m leads collect --profile grain --from-file domains.txt  # из своего списка

# Обогащение почтами
python -m leads enrich                      # все ожидающие
python -m leads enrich --profile grain --limit 50
python -m leads enrich --retry-failed       # повторить blocked / skipped_robots

# Экспорт
python -m leads export --profile petcoke_anode --out leads.csv
python -m leads export --profile petcoke_anode --out all.csv --include-personal

# Сводка
python -m leads stats
python -m leads stats --profile grain
```

`collect` и `enrich` — два шага одного пайплайна, а не независимые прогоны:
каталоги дают домены, `enrich` их обходит. Запускать в этом порядке.

В Telegram: `/leads_stats` — та же сводка, что и `stats`. Уведомлений по каждой
найденной компании нет и не будет.

---

## Источники

| Адаптер | Что делает | Состояние |
|---|---|---|
| `made_in_china` | Обход выдачи каталога по ключевым словам профиля | Селекторы **не проверены на живой вёрстке** |
| `company_site` | Обход сайта компании ради контактов | Проверен на локальном стенде |
| `customs_api` | Импортёры по кодам ТН ВЭД из платной подписки | Заготовка: интерфейс + маппер, без подписки пропускается |

### Чего ожидать от `made_in_china`

Каталог может запрещать обход поисковой выдачи в `robots.txt`. Проверить это
при разработке не удалось — окружение сборки не имеет доступа к
`made-in-china.com`. Если запрещает, адаптер честно ничего не соберёт:

```
[made_in_china] https://www.made-in-china.com/robots.txt: HTTP 403 — access refused
BLOCKED ... — прекращаю обход этого источника
collect: найдено 0
  [BLOCKED] made_in_china: 0 — HTTP 403 — access refused
```

Прогон при этом не падает и продолжается остальными источниками. Обходить
запрет нельзя — см. «Правовые ограничения». Рабочие альтернативы:

1. **Свой список доменов.** Соберите домены откуда угодно легально (отраслевые
   каталоги, участники выставок, купленная таможенная выгрузка) и скормите
   напрямую:
   ```bash
   printf 'hongyun-carbon.cn\nkaifeng-anode.cn\n' > domains.txt
   python -m leads collect --profile petcoke_anode --from-file domains.txt
   python -m leads enrich
   ```
   `enrich` работает независимо от каталога — это основной рабочий путь, если
   каталоги закрыты.

2. **Платная таможенная подписка.** Самый качественный источник: реальные
   декларации по кодам ТН ВЭД. См. ниже.

### Если каталог поменял вёрстку

Селекторы вынесены в `SourceConfig.selectors` (`engine/sources/leads/made_in_china.py`,
словарь `DEFAULT_SELECTORS`) цепочками с запасными вариантами. Правится
конфиг, не код:

```python
MADE_IN_CHINA_CONFIG.selectors["list_item"] = ".new-layout .card"
MADE_IN_CHINA_CONFIG.selectors["company_name"] = ".card__title a"
```

Что `collect` вернул 0 при доступном каталоге — верный признак, что селекторы
разъехались.

### Подключение таможенных данных

```bash
LEADS_CUSTOMS_API_KEY=...
LEADS_CUSTOMS_API_PROVIDER=volza          # или importgenius / panjiva
LEADS_CUSTOMS_API_BASE_URL=https://api.volza.com/v1/shipments
```

Без ключа адаптер сообщает «требует подписки» и пропускается без ошибки.

Карты полей ответа лежат в `PROVIDER_FIELD_MAPS`
(`engine/sources/leads/customs_api.py`). **Ни одна из них не проверена на живом
API** — подписки у проекта нет. Перед первым боевым запуском сверьте имена
полей с документацией провайдера и поправьте карту; переписывать адаптер для
этого не нужно.

---

## Что собирается в карточку

`company_name_en`, `company_name_zh`, `province`, `city`, `website`, `emails[]`,
`phones[]`, `wechat`, `whatsapp`, `matched_keywords[]`, `profile`,
`industry_guess`, `source_url`, `source_name`, `first_seen`, `last_seen`.

### Почты

* забираются из `mailto:` и из текста страницы;
* раскрывается обфускация: `name (at) domain (dot) com`, `name[at]domain[dot]com`,
  `name#domain.com`, `name AT domain DOT com`, HTML-сущности `&#64;`/`&#46;`;
* отсеивается мусор: `noreply@`, `no-reply@`, `@example.com`, `@sentry`,
  `@wixpress`, плейсхолдеры вида `yourname@`, имена файлов (`logo@2x.png`);
* остаются только адреса на домене компании — почта студии-подрядчика со
  страницы контактов компании не принадлежит;
* всё в нижнем регистре, дедуп по паре (домен, локальная часть);
* **у каждого адреса сохраняется `source_url`** — страница, с которой он снят,
  чтобы находку можно было проверить руками.

Классификация:

* `role` — обезличенный ящик: `info@`, `sales@`, `export@`, `trade@`,
  `purchase@`, а также `sales2@`, `export-cn@`, `info.hk@`;
* `personal` — именной: `li.wei@`, `zhangwei@`.

### Дедупликация

Ключ — нормализованный домен сайта. Без сайта — нормализованное название плюс
провинция. Юридические формы из ключа вычищаются, поэтому
`Shandong Petro-Coke Co., Ltd.` и `SHANDONG PETRO COKE INDUSTRIAL CO LTD` —
одна и та же компания.

Повторный `collect` дублей не создаёт: запись обновляется, почты объединяются,
`first_seen` сохраняется от первой находки.

---

## Экспорт в Coldy

```bash
python -m leads export --profile petcoke_anode --out leads.csv
```

Колонки ровно в таком порядке, одна строка — одна почта:

```
Company,Email,Website,Province,City,Profile,Source
```

Кодировка — UTF-8 с BOM, чтобы Excel не ломал китайские названия. Другую можно
задать через `--encoding utf-8`. Строки отсортированы по `regions_priority`, то
есть приоритетные провинции идут сверху. Файл пишется даже когда строк нет —
с одним заголовком, чтобы загрузка не падала на пустом входе.

### Список исключений

`config/leads_blacklist.txt` — по записи на строку, `#` начинает комментарий:

```
example.com            # домен целиком, включая поддомены
opt-out@hongyun.cn     # конкретный адрес
```

Применяется **на экспорте**: адрес остаётся в базе (чтобы следующий обход не
нашёл его заново как новый), но в CSV не попадает. Сюда же добавляйте всех, кто
отписался или попросил его не беспокоить.

---

## Правовые ограничения

Это не рекомендации, а поведение, зашитое в код.

### 1. `robots.txt` соблюдается

Каждый URL проверяется перед запросом. Запрещённые пути не запрашиваются
вообще. Пропуски видны в логе:

```
ROBOTS SKIP https://example.cn/private/: disallowed by robots.txt
```

Если `robots.txt` вернул 5xx или недоступен, домен пропускается целиком:
неизвестно, что разрешено, значит не идём никуда. 404 означает, что файла нет
и обход разрешён — так предписывает стандарт.

`Crawl-delay` соблюдается: используется большее из настроенной задержки и
запрошенной сайтом.

### 2. Вежливый режим

* задержка между запросами — не меньше `request_delay_seconds` (минимум 1 с);
* конкурентность — не больше 2, и один домен всегда обрабатывается одним
  воркером целиком, так что параллельных запросов к одному хосту не бывает;
* `User-Agent` честный и с контактом:
  `TenderProLeadsBot/1.0 (+mailto:ваш-ящик@вашдомен.ru)`.

### 3. Антибот-защита не обходится

Капча, 403 или блокировка — обход этого источника прекращается, событие
пишется в лог, прогон продолжается остальными. В коде нет и не должно быть
ротации прокси, подмены отпечатков и эмуляции браузера ради обхода блокировок:
`PoliteFetcher` не умеет ходить через прокси и не ротирует `User-Agent`
конструктивно, а не по договорённости.

### 4. Только публичные страницы

Никакой авторизации, никаких закрытых разделов. Единственное исключение —
`customs_api`: там ключ передаётся в оплаченный по договору API, а не
используется для входа в чужой личный кабинет.

### 5. PIPL — закон КНР о персональных данных

По умолчанию **в экспорт идут только ролевые адреса**. Персональные собираются
и хранятся, но выгружаются лишь при явном `--include-personal`.

> **Предупреждение о правовых рисках.** Именной адрес (`li.wei@company.cn`) —
> персональные данные по PIPL. Закон требует правового основания на обработку и
> уведомления субъекта; у холодной рассылки такого основания, как правило, нет.
> Статья 66 PIPL предусматривает штрафы до 50 млн юаней или 5% годового
> оборота, а для рассылки применим ещё и Закон о рекламе КНР, требующий
> явного согласия получателя. Ролевые ящики (`info@`, `sales@`, `export@`)
> считаются корпоративными контактами и несут заметно меньший риск — поэтому
> они и стоят по умолчанию.
>
> Флаг `--include-personal` перекладывает это решение на вас. Перед его
> использованием проконсультируйтесь с юристом.

Обязательно к соблюдению в самой рассылке: рабочая ссылка на отписку,
отписавшиеся немедленно вносятся в `config/leads_blacklist.txt`.

### 6. `Retry-After` и 429

429 или 503 с заголовком `Retry-After` — ждём ровно столько, сколько попросили,
и повторяем один раз. Если запрошенная пауза больше 5 минут или повтор снова
дал 429, источник считается заблокированным и обход прекращается.

---

## Расписание

### GitHub Actions

`.github/workflows/parse-leads.yml` — раз в неделю, понедельник 02:30 UTC, плюс
запуск руками. Отдельный workflow, не в общем цикле с тендерами.

Job ничего не делает, пока не выставлена переменная репозитория
`LEADS_ENABLED=true` (Settings → Secrets and variables → Actions → Variables).
Там же задайте `LEADS_CONTACT_EMAIL` — без него прогон падает намеренно.

> Workflow лежат в `.github/workflows/` в **корне репозитория**, а каждый job
> выполняет шаги в `tender-parser` через `defaults.run.working-directory`.
> Так и должно быть: GitHub читает workflow только из корня, а весь проект
> живёт в подкаталоге.
>
> С 2026-05-06 (коммит `ffcc846`, перенёсший проект в подкаталог) по
> 2026-08-17 Actions не запускался вообще — файлы лежали в
> `tender-parser/.github/workflows/`, куда GitHub не смотрит. Сейчас это
> исправлено, и все workflow снова активны.

### systemd (если поднимаете на VPS)

Готовые юниты — `deploy/systemd/leads-collect.service` и `.timer`:

```bash
sudo cp deploy/systemd/leads-collect.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now leads-collect.timer
systemctl list-timers leads-collect.timer
journalctl -u leads-collect.service -f
```

Проект сейчас не развёрнут на systemd — расписание живёт в GitHub Actions.
Юниты приложены для тех, кто перенесёт парсер на свой сервер.

---

## Тесты

```bash
pytest engine/tests/leads/ -v
```

Покрыто: разбор карточки каталога, извлечение и деобфускация почт, фильтрация
мусорных адресов, дедупликация, проверка `robots.txt`, устойчивость к
блокировкам, обратная совместимость `HttpFetcher`, поведение при выключенном
флаге.

Тесты лежат в `engine/tests/leads/`. Гоняются общим workflow
`.github/workflows/test.yml` вместе с остальными наборами:

```bash
pytest tests/ engine/tests/ --ignore=tests/test_db.py    # 328 тестов, все зелёные
```

---

## Диагностика

| Симптом | Причина и что делать |
|---|---|
| `LEADS_ENABLED=false — домен выключен` | Так и задумано. `LEADS_ENABLED=true` в `.env` |
| `collect` вернул 0, в логе `BLOCKED ... 403` | Каталог нас не пускает. Используйте `--from-file` или `customs_api` |
| `collect` вернул 0, каталог доступен | Разъехались селекторы — см. «Если каталог поменял вёрстку» |
| `customs_api: требует подписки` | Ожидаемо без ключа. Задайте `LEADS_CUSTOMS_API_KEY` |
| `enrich`: везде `skipped_robots` | `robots.txt` недоступен или запрещает. Смотрите точную причину в логе |
| `enrich` нашёл 0 почт | Контактов нет на публичных страницах, либо все адреса на чужом домене |
| В CSV пусто, а `stats` показывает почты | Все адреса персональные. Проверьте `stats`, при необходимости `--include-personal` |
| `Таблица leads_companies недоступна` | Примените `scripts/migration_leads.sql` или вернитесь на `LEADS_STORAGE=sqlite` |
| `Не установлен PyYAML` | `pip install -r requirements-parser.txt` |
