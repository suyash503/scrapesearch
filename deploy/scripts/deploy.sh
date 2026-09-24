#!/usr/bin/env bash
# Deploy the latest code: git pull -> pip install -> migrate -> collectstatic -> build frontend
# -> restart gunicorn -> health check. Safe to re-run. Stops at the first failing step (set -e).
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: deploy.sh [BRANCH]

  BRANCH   git branch to deploy (default: main)
  Run as the `deploy` user on the server. Asks for your sudo password once (to restart gunicorn).
  After changing the ES mapping, also run a full reindex:  .venv/bin/python backend/manage.py sync_es
EOF
}
[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }

source "$(dirname "$0")/lib.sh"
BRANCH="${1:-main}"
VENV="$APP_DIR/.venv"
PY="$VENV/bin/python"

[[ "$(id -un)" == "deploy" ]] || fail "run this as the deploy user (sudo -iu deploy)"
cd "$APP_DIR"

log "1/7 git: $BRANCH"
git fetch --prune origin
git checkout "$BRANCH"
# --ff-only: refuse to invent a merge commit on the server if its history has diverged.
git pull --ff-only origin "$BRANCH"
log "    now at $(git log -1 --format='%h %s')"

log "2/7 python dependencies"
[[ -d "$VENV" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r scraper/requirements.txt -r backend/requirements.txt

log "3/7 database migrations"
"$PY" backend/manage.py migrate --noinput

log "4/7 static files (Django admin)"
"$PY" backend/manage.py collectstatic --noinput --clear > /dev/null

log "5/7 frontend build"
# npm ci installs exactly what package-lock.json says (reproducible), unlike npm install.
(cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build)

mkdir -p "$APP_DIR/logs"

log "6/7 restart gunicorn"
# reload-or-restart: if it's running, HUP it (new workers start, old ones finish their requests =
# no dropped requests); if it isn't running, start it.
sudo systemctl reload-or-restart gunicorn

log "7/7 health check"
# Workers need a moment to boot. Retry for ~20s instead of a single fixed sleep.
for attempt in {1..10}; do
    if "$APP_DIR/deploy/scripts/healthcheck.sh" --quiet; then
        log "Deployed $(git log -1 --format='%h') successfully."
        exit 0
    fi
    log "    not healthy yet (attempt $attempt/10), retrying in 2s"
    sleep 2
done
fail "health check still failing. Look at: journalctl -u gunicorn -n 50 --no-pager"
