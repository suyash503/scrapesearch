#!/usr/bin/env bash
# Dump the MySQL database to a gzipped file and delete dumps older than 7 days.
# Restore:  gunzip -c scrapesearch_2026-09-23_0315.sql.gz | mysql -u <user> -p scrapesearch
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: backup_mysql.sh [BACKUP_DIR]

  BACKUP_DIR   where to put the dumps (default: /home/deploy/backups/mysql)
  Keeps the last 7 days of backups. Reads MYSQL_* from the app's .env.
EOF
}
[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }

source "$(dirname "$0")/lib.sh"
load_env "$APP_DIR/.env"

BACKUP_DIR="${1:-/home/deploy/backups/mysql}"
KEEP_DAYS=7
DB="${MYSQL_DATABASE:?MYSQL_DATABASE not set}"
STAMP="$(date '+%F_%H%M')"
OUT="$BACKUP_DIR/${DB}_${STAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"  # dumps contain all the data: owner-only
umask 077                # ...and so does every file we create below

# Pass the password in a temporary option file, NOT as -p<password> on the command line:
# command-line arguments are visible to every user on the machine via `ps aux`.
CNF="$(mktemp)"
trap 'rm -f "$CNF" "$OUT.partial"' EXIT  # always clean up, even if the dump fails halfway
printf '[client]\nuser=%s\npassword=%s\nhost=%s\nport=%s\n' \
    "$MYSQL_USER" "$MYSQL_PASSWORD" "${MYSQL_HOST:-127.0.0.1}" "${MYSQL_PORT:-3306}" > "$CNF"

log "Backing up $DB -> $OUT"
# --single-transaction  consistent snapshot of InnoDB tables WITHOUT locking them (the site stays up)
# --quick               stream rows instead of loading whole tables into memory
# --no-tablespaces      skip tablespace info, which needs the PROCESS privilege our app user doesn't have
# pipefail (set above) makes the pipeline fail if mysqldump fails, not just if gzip does.
mysqldump --defaults-extra-file="$CNF" --single-transaction --quick --routines --triggers \
    --no-tablespaces "$DB" | gzip > "$OUT.partial"

# Write to .partial first and rename at the end: a crashed or half-written dump never looks like a good backup.
gzip -t "$OUT.partial"  # verify the archive is readable
mv "$OUT.partial" "$OUT"
log "Done: $(du -h "$OUT" | cut -f1)"

# Retention: delete dumps last modified more than KEEP_DAYS-1 full days ago, i.e. keep the last 7.
deleted="$(find "$BACKUP_DIR" -name "${DB}_*.sql.gz" -mtime +$((KEEP_DAYS - 1)) -print -delete | wc -l)"
log "Removed $deleted old backup(s). Now keeping: $(find "$BACKUP_DIR" -name "${DB}_*.sql.gz" | wc -l)"
