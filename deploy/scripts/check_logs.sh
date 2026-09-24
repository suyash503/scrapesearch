#!/usr/bin/env bash
# Count ERROR lines from the last N hours: gunicorn (journald) and the scraper/cron log files.
# Exit code 1 if any errors were found, so it can drive alerts.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: check_logs.sh [HOURS]

  HOURS   how far back to look (default: 24)
  Sources: journalctl -u gunicorn, scraper/logs/*.log, logs/*.log
EOF
}
[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }

HOURS="${1:-24}"
[[ "$HOURS" =~ ^[0-9]+$ ]] || { usage >&2; exit 2; }

source "$(dirname "$0")/lib.sh"

# Cutoff as "YYYY-MM-DD HH:MM:SS". Our log lines all start with a timestamp in this format, and
# ISO-style timestamps sort alphabetically in time order, so a plain string compare works in awk.
SINCE="$(date -d "-$HOURS hours" '+%F %T')"
PATTERN='ERROR|CRITICAL|Traceback'
total=0

report() {  # report SOURCE COUNT SAMPLE_LINES
    local source="$1" count="$2" sample="$3"
    printf '%-40s %5d\n' "$source" "$count"
    if [[ "$count" -gt 0 ]]; then
        # shellcheck disable=SC2001  # sed reads clearer than ${var//} for indenting every line
        sed 's/^/    /' <<<"$sample"  # indent the last few matching lines under the count
    fi
    total=$((total + count))
}

echo "Errors since $SINCE ($HOURS h)"
echo "------------------------------------------------"

# 1) gunicorn/Django via journald. journalctl filters by time itself.
if command -v journalctl >/dev/null; then
    lines="$(journalctl -u gunicorn --since "$SINCE" --no-pager -q 2>/dev/null | grep -E "$PATTERN" || true)"
    # `|| true`: grep exits 1 when nothing matches. With `set -e` + `pipefail`, "no errors" would kill the script.
    report "journald: gunicorn" "$(grep -c . <<<"$lines" || true)" "$(tail -n 3 <<<"$lines")"
fi

# 2) log files written by Scrapy, the Selenium script and cron.
shopt -s nullglob  # a glob with no matches expands to nothing instead of the literal pattern
for file in "$APP_DIR"/scraper/logs/*.log "$APP_DIR"/logs/*.log; do
    lines="$(awk -v since="$SINCE" -v pat="$PATTERN" 'substr($0, 1, 19) >= since && $0 ~ pat' "$file")"
    report "${file#"$APP_DIR"/}" "$(grep -c . <<<"$lines" || true)" "$(tail -n 3 <<<"$lines")"
done

echo "------------------------------------------------"
printf '%-40s %5d\n' "TOTAL" "$total"
[[ "$total" -eq 0 ]]
