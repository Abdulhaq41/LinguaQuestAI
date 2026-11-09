#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backup_dir="${BACKUP_DIR:?Set BACKUP_DIR outside the checkout}"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
backup_file="$backup_dir/linguaquest-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
umask 077
docker compose exec -T postgres pg_dump -U linguaquest -d linguaquest | gzip > "$backup_file"
gzip -t "$backup_file"
echo "Backup saved. Regularly test restore into a separate database."
