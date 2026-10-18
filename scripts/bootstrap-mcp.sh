#!/usr/bin/env bash
# Install the optional MCP extra into the adapter venv.
# Not used by bale-platform.service or deploy.yml. See docs/mcp.md.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${BALE_MCP_VENV:-$ROOT/venv}"

if [ ! -x "$VENV/bin/pip" ]; then
  echo "adapter venv not found at $VENV — start bale-platform once, or set BALE_MCP_VENV" >&2
  exit 1
fi

"$VENV/bin/pip" install --disable-pip-version-check 'mcp>=2,<3'
echo "mcp extra installed in $VENV"
