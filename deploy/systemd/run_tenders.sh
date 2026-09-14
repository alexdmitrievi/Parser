#!/usr/bin/env bash
# Запуск тендерных парсеров с корректным TLS-окружением.
#
# ЕИС (zakupki.gov.ru) отдаёт сертификат «Russian Trusted Sub CA» (Минцифры),
# которого нет в certifi — CA-бандле, которым по умолчанию пользуется httpx.
# Поэтому направляем httpx в системное хранилище, где установлены российские
# корневые сертификаты (см. docs/INFRASTRUCTURE.md). Для ручного запуска
# достаточно этой обёртки; в systemd-юните значение продублировано.
set -euo pipefail

APP_DIR="/opt/tender-parser"
export SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
export PYTHONUNBUFFERED=1

cd "$APP_DIR"
exec "$APP_DIR/.venv/bin/python" scripts/run_parser.py "$@"
