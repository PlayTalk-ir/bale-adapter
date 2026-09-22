#!/usr/bin/env bash
# Activate bale-adapter venv + local env vars (Linux/macOS).
# Usage:  source scripts/activate.sh

_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -f "$_ROOT/venv/bin/activate" ]; then
    echo "[err] venv not found - run ./scripts/bootstrap-local.sh first" >&2
    return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1091
source "$_ROOT/venv/bin/activate"

export BALE_SESSION_PATH="$_ROOT/.session/session.bale"
export BALE_KB_DIR="$_ROOT/kb"
export BALE_LOG_FILE="$_ROOT/logs/userbot.log"
export BALE_STORE_PATH="$_ROOT/data/support_inbox.sqlite"
export PYTHONPATH="$_ROOT"

echo "bale-adapter venv active ($_ROOT)"
