#!/usr/bin/env python3
"""Run the Bale adapter MCP server (stdio or loopback streamable HTTP).

    python scripts/mcp_server.py
    python scripts/mcp_server.py http

See docs/mcp.md. This process calls the adapter HTTP API; it does not open
the userbot session.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform.mcp_server.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
