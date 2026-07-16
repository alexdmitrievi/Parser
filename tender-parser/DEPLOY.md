# Развёртывание мониторинга закупок на VPS (Ubuntu 24.04 LTS)

Пошаговая установка от `apt update` до первой карточки в Telegram.
Целевая среда: Яндекс Облако, 2 vCPU / 4 ГБ RAM / 60 ГБ SSD, один пользователь.

Архитектура на VPS:

```
systemd timer (120 мин) → monitor/run_cycle.py:
    FTP ЕИС (44-ФЗ + 223-ФЗ, Омская/Новосибирская обл.)
    → парсинг XML → фильтры config/filters.yaml
    → локальный PostgreSQL → карточки в Telegram
systemd service → monitor/bot.py (бот: /stats, /status; отвечает только вам)
systemd timer (ежедневно) → pg_dump с ротацией 14 дней
```

Vercel и Supabase для мониторинга не используются (грантовая часть проекта
продолжает жить на Supabase независимо и на VPS не разворачивается).

---

## 1. Базовая система

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git python3.12-venv python3-pip postgresql postgresql-client
```

## 2. Пользователь и каталоги

```bash
sudo useradd --system --create-home --shell /bin/bash tender
sudo mkdir -p /opt/tender-parser /var/log/tender-monitor /var/backups/tender-monitor /tmp/tender-monitor
sudo chown -R tender:tender /opt/tender-parser /var/log/tender-monitor /var/backups/tender-monitor /tmp/tender-monitor
```

## 3. PostgreSQL

```bash
sudo -u postgres psql -c "CREATE USER tender WITH PASSWORD 'ЗАМЕНИТЕ_НА_СВОЙ_ПАРОЛЬ';"
sudo -u postgres psql -c "CREATE DATABASE tender_monitor OWNER tender;"
```

Проверка: `psql postgresql://tender:ПАРОЛЬ@localhost:5432/tender_monitor -c 'select 1;'`

Таблицы создаются автоматически при первом запуске цикла — отдельных миграций не нужно.

## 4. Код и зависимости

```bash
sudo -u tender git clone https://github.com/alexdmitrievi/parser.git /opt/tender-parser/src
sudo -u tender bash -c '
  cd /opt/tender-parser &&
  cp -r src/tender-parser/* src/tender-parser/.env.example . 2>/dev/null;
  python3 -m venv .venv &&
  .venv/bin/pip install -r requirements-monitor.txt
'
```

> Если репозиторий приватный — используйте deploy key или `git clone` по SSH.

## 5. Секреты (.env)

```bash
sudo -u tender cp /opt/tender-parser/.env.example /opt/tender-parser/.env
sudo -u tender nano /opt/tender-parser/.env
sudo chmod 600 /opt/tender-parser/.env
```

Обязательно заполнить:
- `TELEGRAM_BOT_TOKEN` — токен бота от @BotFather;
- `TELEGRAM_CHAT_ID` — ваш chat_id (узнать: написать @userinfobot). Бот отвечает только этому id;
- `DATABASE_URL` — строка подключения из шага 3.

`.env` в git не коммитится (есть в `.gitignore`).

## 6. Проверка FTP ЕИС (важно!)

Имена региональных каталогов на FTP транслитерируются неконсистентно,
поэтому перед первым циклом запустите разведку:

```bash
cd /opt/tender-parser && sudo -u tender .venv/bin/python scripts/eis_ftp_probe.py
```

Ожидаемо: `Connected OK`, для 44-ФЗ и 223-ФЗ найдены каталоги Омской и
Новосибирской областей и показано число архивов. Если логин `free/free`
не подошёл — попробуйте в `.env` `EIS_FTP_USER=anonymous`, `EIS_FTP_PASS=`
(актуальные реквизиты — в документации открытых данных ЕИС на zakupki.gov.ru).

## 7. Бизнес-фильтры

Файл `/opt/tender-parser/config/filters.yaml` — регионы, законы, диапазон НМЦК,
ОКПД2-префиксы, ключевые слова и стоп-слова. Файл перечитывается на каждом
цикле: правки применяются без рестарта сервиса.

## 8. Первый цикл вручную

```bash
cd /opt/tender-parser && sudo -u tender .venv/bin/python -m monitor.run_cycle
```

Первый прогон скачивает бэклог за текущий месяц (ограничен
`EIS_FTP_MAX_ARCHIVES=300` архивов за цикл) и может идти 10–40 минут.
По завершении в Telegram придут карточки по закупкам, прошедшим фильтры.
Обработанные архивы удаляются с диска сразу после разбора.

Проверка состояния: `sudo -u tender .venv/bin/python scripts/healthcheck.py`

## 9. systemd: сервисы и таймеры

```bash
sudo cp /opt/tender-parser/deploy/vps/*.service /opt/tender-parser/deploy/vps/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tender-monitor.timer   # цикл раз в 120 минут
sudo systemctl enable --now tender-bot.service     # бот (/stats, /status)
sudo systemctl enable --now tender-backup.timer    # ежедневный pg_dump, ротация 14 дней
```

Проверка:

```bash
systemctl list-timers tender-*          # когда следующий запуск
systemctl status tender-bot             # бот работает
journalctl -u tender-monitor -n 50      # логи последнего цикла
```

Логи пишутся в journald и (если задан `MONITOR_LOG_FILE`) в файл
с ротацией 10 МБ × 5 файлов.

## 10. Проверка приёмки

1. **Первая карточка**: после шага 8 в Telegram пришла карточка
   (НМЦК · регион · способ закупки · дедлайн · обеспечение · ссылка).
2. **Фильтры на лету**: измените `nmck.min` в `config/filters.yaml` —
   следующий цикл использует новое значение без рестарта.
3. **Нет дублей**: повторный запуск `monitor.run_cycle` не присылает
   повторные карточки (таблицы `eis_processed_archives` и `notified_tenders`).
4. **Устойчивость**: при недоступном FTP цикл завершается с ошибкой в логе,
   сервис не падает; после **двух** неудачных циклов подряд приходит
   сервисный алерт в Telegram, после восстановления — сообщение «снова работает».
5. **Статистика**: команда `/stats` в боте — сводка за 30 дней;
   `/status` — итоги последнего цикла.

## 11. Восстановление из бэкапа

```bash
ls /var/backups/tender-monitor/
pg_restore --clean --dbname="$DATABASE_URL" /var/backups/tender-monitor/tender_monitor_ДАТА.dump
```

## 12. Обновление кода

```bash
cd /opt/tender-parser/src && sudo -u tender git pull
sudo -u tender rsync -a --exclude .env --exclude .venv /opt/tender-parser/src/tender-parser/ /opt/tender-parser/
sudo -u tender /opt/tender-parser/.venv/bin/pip install -r /opt/tender-parser/requirements-monitor.txt
sudo systemctl restart tender-bot
```

---

## Диагностика

| Симптом | Что смотреть |
|---|---|
| Нет карточек | `journalctl -u tender-monitor` — сколько parsed/inserted; `/status` в боте; фильтры не слишком ли узкие |
| FTP не подключается | `scripts/eis_ftp_probe.py`; исходящий порт 21 + пассивный режим в фаерволе Яндекс Облака |
| Бот молчит | `TELEGRAM_CHAT_ID` совпадает с вашим? `systemctl status tender-bot` |
| Диск заполняется | архивы должны удаляться сразу; проверьте `MONITOR_TMP_DIR` и `/var/backups` |
| БД недоступна | `systemctl status postgresql`, `DATABASE_URL` в `.env` |
