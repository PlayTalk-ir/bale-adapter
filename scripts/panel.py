#!/usr/bin/env python3
"""scripts/panel.py — web admin panel for the Bale support adapter.

Local run:
    python scripts/panel.py                     # http://127.0.0.1:8090
    python scripts/panel.py --port 9000

Auth:
    BALE_PANEL_TOKEN=... python scripts/panel.py        # fixed operator token
    python scripts/panel.py                             # random token, printed once
    python scripts/panel.py --no-auth                   # local dev only!

On the VPS run it bound to 127.0.0.1 and reach it over an SSH tunnel:
    ssh -L 8090:127.0.0.1:8090 root@VPS
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aiohttp import web  # noqa: E402

from bale_platform import panel_auth  # noqa: E402
from bale_platform.panel import DEFAULT_HOST, DEFAULT_PORT, build_app  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PlayTalk Bale admin panel")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--token", default="", help="operator token (or BALE_PANEL_TOKEN)")
    parser.add_argument(
        "--no-auth", action="store_true", help="disable login (local dev only)"
    )
    parser.add_argument(
        "--dialog-limit",
        type=int,
        default=200,
        help="dialogs scanned by the contacts refresh job",
    )
    args = parser.parse_args(argv)

    token = args.token or os.getenv("BALE_PANEL_TOKEN", "")
    generated = False
    if not token:
        token = panel_auth.generate_token()
        generated = True
    if not panel_auth.token_ok(token) and not args.no_auth:
        print(
            f"[err] token too short ({len(token)} chars) — need >= "
            f"{panel_auth.MIN_TOKEN_LENGTH}",
            file=sys.stderr,
        )
        return 2

    print("=" * 56)
    print("PlayTalk Bale admin panel")
    print(f"  url:    http://{args.host}:{args.port}")
    if args.no_auth:
        print("  auth:   DISABLED (--no-auth) — local development only")
    elif generated:
        print(f"  token:  {token}")
        print("          (random; set BALE_PANEL_TOKEN to pin it)")
    else:
        print("  token:  from BALE_PANEL_TOKEN / --token")
    print("=" * 56)

    app = build_app(
        token=token,
        no_auth=args.no_auth,
        dialog_limit=args.dialog_limit,
    )
    web.run_app(app, host=args.host, port=args.port, print=lambda *_: None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
