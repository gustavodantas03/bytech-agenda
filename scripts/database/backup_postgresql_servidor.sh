#!/bin/bash
# Backup diário do banco PostgreSQL do Bytech Agenda, com rotação de 14 dias.
set -e

BACKUP_DIR="$HOME/backups/postgres"
DATA=$(date +%Y%m%d_%H%M%S)
ARQUIVO="$BACKUP_DIR/bytech_agenda_$DATA.sql.gz"

mkdir -p "$BACKUP_DIR"

PGPASSWORD="BytechAgenda2026Db" pg_dump -h 127.0.0.1 -U bytech -d bytech_agenda | gzip > "$ARQUIVO"

# Remove backups com mais de 14 dias
find "$BACKUP_DIR" -name "bytech_agenda_*.sql.gz" -mtime +14 -delete

echo "Backup concluído: $ARQUIVO"
