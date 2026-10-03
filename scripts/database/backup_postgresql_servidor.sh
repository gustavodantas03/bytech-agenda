#!/bin/bash
# Backup diário do banco PostgreSQL do Bytech Agenda, com rotação de 14 dias.
set -e

BACKUP_DIR="/root/backups/postgres"
DATA=$(date +%Y%m%d_%H%M%S)
ARQUIVO="$BACKUP_DIR/bytech_agenda_$DATA.sql.gz"

mkdir -p "$BACKUP_DIR"

docker exec bytech-postgres pg_dump \
  -U bytech \
  -d bytech_agenda \
  | gzip > "$ARQUIVO"

# Remove backups com mais de 14 dias
find "$BACKUP_DIR" -name "bytech_agenda_*.sql.gz" -mtime +14 -delete

echo "Backup concluído: $ARQUIVO"
