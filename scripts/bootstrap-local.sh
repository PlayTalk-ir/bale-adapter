#!/usr/bin/env bash
# Local dev bootstrap (repo root) — uv, Python, venv, deps, activate, login.
# NOT used on the VPS (systemd uses scripts/bootstrap.sh → /opt/bale-adapter).
#
# Usage:
#   ./scripts/bootstrap-local.sh
#   source scripts/activate.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
SKIP_LOGIN=0
for arg in "$@"; do
    case "$arg" in
        --skip-login) SKIP_LOGIN=1 ;;
    esac
done

UV="$("$ROOT/scripts/ensure-uv.sh")"
export PATH="$(dirname "$UV"):$PATH"

VENV="$ROOT/venv"
PYTHON="$VENV/bin/python"

echo "[bootstrap] installing Python $PYTHON_VERSION via uv"
"$UV" python install "$PYTHON_VERSION"

export UV_PROJECT_ENVIRONMENT=venv

if [ ! -x "$PYTHON" ]; then
    echo "[bootstrap] creating venv at $VENV"
    "$UV" venv "$VENV" --python "$PYTHON_VERSION"
fi

echo "[bootstrap] syncing dependencies via uv"
"$UV" sync --python "$PYTHON" --directory "$ROOT" --group dev

mkdir -p "$ROOT/.session" "$ROOT/data" "$ROOT/logs" "$ROOT/kb"
chmod 0700 "$ROOT/.session"

# shellcheck disable=SC1091
source "$ROOT/scripts/activate.sh"

SESSION="$BALE_SESSION_PATH"
if [ "$SKIP_LOGIN" -eq 0 ]; then
    if [ ! -s "$SESSION" ]; then
        echo "[bootstrap] no session - starting interactive login"
        python scripts/login.py
    else
        echo "[bootstrap] session exists at $SESSION - skipping login"
    fi
else
    echo "[bootstrap] --skip-login set"
fi

echo "[bootstrap] ok - python=$PYTHON uv=$UV"
echo "Later sessions: source scripts/activate.sh"
