#!/usr/bin/env bash
# Ежедневный дамп локальной PostgreSQL с ротацией 14 дней.
# Запускается systemd-таймером tender-backup.timer от пользователя tender.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/tender-monitor}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
DATABASE_URL="${DATABASE_URL:?DATABASE_URL is not set}"

mkdir -p "$BACKUP_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="$BACKUP_DIR/tender_monitor_${STAMP}.dump"

pg_dump --format=custom --compress=6 --file="$DUMP_FILE" "$DATABASE_URL"

# Ротация: удаляем дампы старше KEEP_DAYS дней
find "$BACKUP_DIR" -name 'tender_monitor_*.dump' -mtime "+${KEEP_DAYS}" -delete

echo "Backup done: $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))"
