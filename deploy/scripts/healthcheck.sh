#!/usr/bin/env bash
# Is ScrapeSearch healthy? Checks the Django API, the Elasticsearch cluster and that the books index has data.
# Exit code 0 = everything OK, 1 = at least one check failed (so cron, deploy.sh or a monitor can react).
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: healthcheck.sh [--quiet]

  --quiet, -q   print nothing when healthy (for cron: only failures land in the log)
  --help,  -h   show this help

Env overrides: API_URL (default http://127.0.0.1:8000/api/health), APP_DIR, ES_URL, ES_PASSWORD, ES_CA_CERTS
EOF
}

QUIET=0
case "${1:-}" in
    -q|--quiet) QUIET=1 ;;
    -h|--help)  usage; exit 0 ;;
    "")         ;;
    *)          usage >&2; exit 2 ;;
esac

source "$(dirname "$0")/lib.sh"
# ES URL and credentials come from the app's .env (if present), so this matches what Django uses.
[[ -f "$APP_DIR/.env" ]] && load_env "$APP_DIR/.env"
API_URL="${API_URL:-http://127.0.0.1:8000/api/health}"
ES_URL="${ES_URL:-http://127.0.0.1:9200}"

# curl flags: -f fail on HTTP >= 400, -s silent, -S but still show errors, --max-time never hang
CURL=(curl -fsS --max-time 5)
if [[ -n "${ES_PASSWORD:-}" ]]; then
    ES_CURL=("${CURL[@]}" -u "${ES_USERNAME:-elastic}:$ES_PASSWORD")
else
    ES_CURL=("${CURL[@]}")
fi
[[ -n "${ES_CA_CERTS:-}" ]] && ES_CURL+=(--cacert "$ES_CA_CERTS")

failures=0

# check NAME COMMAND...  runs COMMAND, reports OK/FAIL with its output.
check() {
    local name="$1" output
    shift
    if output="$("$@" 2>&1)"; then
        [[ "$QUIET" == 1 ]] || log "OK    $name: $output"
    else
        log "FAIL  $name: ${output:-no output}"
        # Note: not ((failures++)). With `set -e`, ((0++)) evaluates to 0 = "false" and kills the script.
        failures=$((failures + 1))
    fi
}

api_health() {
    "${CURL[@]}" "$API_URL"
}

es_cluster_health() {
    local body status
    body="$("${ES_CURL[@]}" "$ES_URL/_cluster/health")"
    # Pull "status":"green" out of the JSON without needing jq.
    status="$(grep -o '"status":"[a-z]*"' <<<"$body" | cut -d'"' -f4)"
    # green = all good, yellow = all data available but replicas missing (normal on one node), red = data missing
    [[ "$status" == green || "$status" == yellow ]] || { echo "status=${status:-unknown}"; return 1; }
    echo "$status"
}

books_index_has_docs() {
    local count
    count="$("${ES_CURL[@]}" "$ES_URL/books/_count" | grep -o '"count":[0-9]*' | cut -d: -f2)"
    [[ "${count:-0}" -gt 0 ]] || { echo "books index is empty (run: manage.py sync_es)"; return 1; }
    echo "$count docs"
}

check "api"           api_health
check "elasticsearch" es_cluster_health
check "books index"   books_index_has_docs

[[ "$failures" -eq 0 ]] || exit 1
