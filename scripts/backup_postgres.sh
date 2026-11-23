#!/usr/bin/env bash
# Nightly backup: PostgreSQL custom-format dump + attachments archive, keeps 30 days.
#   UCF_DB=ucfin PGHOST=localhost PGUSER=ucfin_app PGPASSWORD=... ./scripts/backup_postgres.sh /backups
set -euo pipefail
DEST="${1:-/backups}"; DB="${UCF_DB:-ucfin}"; ATT="${UCF_ATTACHMENT_DIR:-/var/lib/ucfin/attachments}"
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$DEST"
pg_dump --format=custom --no-owner --file "$DEST/ucfin_${STAMP}.dump" "$DB"
[ -d "$ATT" ] && tar -czf "$DEST/attachments_${STAMP}.tar.gz" -C "$(dirname "$ATT")" "$(basename "$ATT")"
pg_restore --list "$DEST/ucfin_${STAMP}.dump" > /dev/null   # verifies the dump is readable
find "$DEST" -name 'ucfin_*.dump' -mtime +30 -delete
find "$DEST" -name 'attachments_*.tar.gz' -mtime +30 -delete
echo "Backup written: $DEST/ucfin_${STAMP}.dump"
