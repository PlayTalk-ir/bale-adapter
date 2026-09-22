#!/usr/bin/env bash
# Ensure uv is on PATH. Prints uv executable path to stdout.
# Usage: UV="$(./scripts/ensure-uv.sh)"

set -euo pipefail

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    for p in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [ -x "$p" ]; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

UV="$(find_uv || true)"
if [ -z "$UV" ]; then
    echo "[bootstrap] installing uv (https://astral.sh/uv)" >&2
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    UV="$(find_uv || true)"
fi

if [ -z "$UV" ]; then
    echo "[err] uv not found after install - open a new shell and re-run bootstrap" >&2
    exit 1
fi

echo "$UV"
