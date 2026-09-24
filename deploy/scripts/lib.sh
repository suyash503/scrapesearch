#!/usr/bin/env bash
# Shared helpers for the deploy scripts. Not run directly: the other scripts `source` it.

# Where the app lives on the server. Override for testing: APP_DIR=/some/path deploy.sh
APP_DIR="${APP_DIR:-/home/deploy/scrapesearch}"

# Read KEY=value lines from a .env file into the environment.
# Why not just `source .env`? Sourcing EXECUTES the file as bash: a value containing $(...) or `...`
# would run as a command. This only splits on the first "=" and never evaluates anything.
load_env() {
    local file="$1" line key value
    [[ -f "$file" ]] || { echo "load_env: $file not found" >&2; return 1; }
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"                               # tolerate CRLF if edited on Windows
        [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue    # skip comments and blank lines
        key="${line%%=*}"
        value="${line#*=}"
        [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue  # ignore anything that isn't KEY=...
        # Don't override variables already set (same rule as python-dotenv).
        [[ -z "${!key+x}" ]] && export "$key=$value"
    done < "$file"
}

log()  { printf '%s  %s\n' "$(date '+%F %T')" "$*"; }
fail() { printf '%s  ERROR: %s\n' "$(date '+%F %T')" "$*" >&2; exit 1; }
