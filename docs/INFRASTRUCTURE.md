# Инфраструктура сбора (VM, сеть, доступ к площадкам)

Описывает выделенную инфраструктуру сбора данных: VM в Yandex Cloud, установку
российских корневых сертификатов для ЕИС и матрицу доступности площадок.
Сверено с продом 2026-09-01.

## 1. Выделенная VM `parser-scraper`

Сбор идёт с отдельной VM, чтобы выходить в сеть с российского IP и не трогать
боевые VM других проектов (`tbx-prod`, `podryadpro-prod`).

| Параметр | Значение |
|---|---|
| Провайдер | Yandex Cloud, folder `default`, zone `ru-central1-a` (Москва) |
| Образ | Ubuntu 22.04.5 LTS |
| Внешний IP | 89.169.145.85 |
| SSH | `ubuntu@89.169.145.85`, ключ `/opt/data/home/.ssh/id_ed25519_parser` |
| Security Group | `parser-scraper-sg` (SSH 22 открыт) |

Порядок подъёма VM и типовые грабли Yandex Cloud (поле `imageId`, а не
`sourceImageId`, для boot-диска; асинхронные операции; квота SSD) — в навыке
`yandex-cloud-management`.

## 2. Доступ к ЕИС (zakupki.gov.ru): российские сертификаты

ЕИС отдаёт сертификат от «Russian Trusted Sub CA» (Минцифры), которого нет в
стандартных CA-бандлах — TLS-рукопожатие падает с «unknown CA». Лечится
установкой российских корневых сертификатов, а не отключением проверки TLS
(`verify=False` не вариант).

Источник сертификатов — реестр Минцифры (gu-st.ru):

- Root: `https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer`
- Sub:  `https://gu-st.ru/content/Other/doc/russian_trusted_sub_ca.cer`

На VM выполнено:

```bash
sudo mkdir -p /usr/local/share/ca-certificates/russian
sudo curl -sS https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer \
  -o /usr/local/share/ca-certificates/russian/root.crt
sudo curl -sS https://gu-st.ru/content/Other/doc/russian_trusted_sub_ca.cer \
  -o /usr/local/share/ca-certificates/russian/sub.crt
sudo update-ca-certificates
```

Сверка sha256 URL и установленных файлов даёт одинаковые хеши. После этого
`https://zakupki.gov.ru/` отвечает HTTP 200 (корневой путь отдаёт 404 — это
норма; рабочий endpoint — `/epz/order/extendedsearch/results.html`).

## 3. Матрица доступности площадок (с VM, российский эгресс)

| Площадка | Статус | access_mode |
|---|---|---|
| zakupki.gov.ru (ЕИС) | 200 ✅ | geo |
| sberbank-ast.ru | 200 ✅ | direct |
| roseltorg.ru | 200 ✅ | direct |
| tektorg.ru | 200 ✅ | direct |
| fabrikant.ru | 200 ✅ | direct |
| corpmsp / frprf / mspbank / mybusiness (гранты) | 200 ✅ | direct |
| lot-online.ru | 200 ✅ | direct |
| b2b-center.ru | 403 — антибот | proxy |
| rts-tender.ru | 503 — антибот | proxy |

`access_mode` — классификация доступа по `docs/SCRAPING_POLICY.md` §2
(`direct` / `geo` / `proxy`), задаётся в `engine.types.AccessMode`.

## 4. Что ещё не сделано

- Репозиторий и зависимости на VM не развёрнуты — отдельный этап развёртывания.
- Антибот-площадки (`b2b-center`, `rts-tender`) требуют прокси/ScrapingBee —
  это работа в коде (достройка `engine/`), не в инфраструктуре.
- EIS FTP (`ftp.zakupki.gov.ru`) мёртв (NXDOMAIN); официальный API/дамп ЕИС —
  отдельный трек, не покрытый этой VM.
