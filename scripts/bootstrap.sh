#!/usr/bin/env bash
# bale-adapter bootstrap — idempotent.
# Runs as ExecStartPre= before the bale-platform runner starts.
#
# Responsibilities:
#   1. Ensure /opt/bale-adapter/.session/ exists with mode 0700.
#   2. Ensure Python venv at /opt/bale-adapter/venv.
#   3. Install aiobale (from GitHub; PyPI version is an empty shell), httpx, pyyaml.
#   4. Ensure kb/ + logs/ directories exist.
#   5. Make scripts/login.py executable.
#
# NEVER touches Bale credentials — those are entered by the operator via
# scripts/login.py on the VPS console.

set -euo pipefail
# NOTE: ExecStartPre in bale-platform.service invokes this script directly.
# /opt may be on a noexec mount; the deploy workflow installs a copy of this
# script to /usr/local/bin/bale-adapter-bootstrap.sh so systemd can exec it.

cd /opt/bale-adapter

SESSION_DIR="/opt/bale-adapter/.session"
mkdir -p "$SESSION_DIR"
chmod 0700 "$SESSION_DIR"

mkdir -p /opt/bale-adapter/kb /opt/bale-adapter/logs

VENV="/opt/bale-adapter/venv"
if [ ! -d "$VENV" ]; then
    echo "[bootstrap] creating venv at $VENV"
    # Some VPS images (Debian 13+) ship python3 without ensurepip and without
    # python3-venv. We fall back to a system pip if venv creation lacks pip.
    if ! python3 -m venv --system-site-packages "$VENV" 2>/dev/null; then
        echo "[bootstrap] venv with --system-site-packages failed; trying --without-pip"
        python3 -m venv --without-pip "$VENV"
    fi
fi

# Ensure pip exists in the venv. If not, bootstrap it via get-pip.py.
if [ ! -x "$VENV/bin/pip" ]; then
    echo "[bootstrap] venv pip missing — bootstrapping via get-pip.py"
    if ! "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
        "$VENV/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi
    if [ ! -x "$VENV/bin/pip" ]; then
        # Last resort: download get-pip.py and run it
        curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
        "$VENV/bin/python" /tmp/get-pip.py
        rm -f /tmp/get-pip.py
    fi
fi

# install deps (idempotent; pip is fast on cached wheels)
"$VENV/bin/pip" install --quiet --upgrade pip >/dev/null 2>&1 || true

# aiobale: PyPI's bare `aiobale` is an empty shell and Enalite/aiobale was
# taken down. The maintained continuation is `aiobale-py` on PyPI
# (aminmadaniofficial/aiobale, 0.3.8+, compatible with our session files).
# The vendor zip stays as an offline fallback only.
"${VENV}/bin/pip" install --quiet 'aiobale-py>=0.3.8' >/dev/null 2>&1 || \
    "${VENV}/bin/pip" install --quiet ./vendor/aiobale-source.zip >/dev/null 2>&1 || \
    "${VENV}/bin/python" /opt/bale-adapter/vendor/install_aiobale.py "${VENV}/bin/pip" || \
    echo "[bootstrap] WARN: aiobale install failed — run scripts/login.py will error until fixed"
"${VENV}/bin/pip" install --quiet 'pydantic' 'aiohttp' 'aiofiles<24' 'httpx' 'pyyaml' 'blackboxprotobuf' 'colorama' 'magic-filter' 'python-ulid>=2' >/dev/null 2>&1 || true

chmod +x /opt/bale-adapter/scripts/login.py 2>/dev/null || true

echo "[bootstrap] ok — venv=$VENV aiobale installed; session dir = $SESSION_DIR"
