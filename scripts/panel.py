#!/usr/bin/env python3
"""scripts/panel.py — web admin panel for the Bale support adapter.

Local run:
    python scripts/panel.py                     # http://127.0.0.1:8090
    python scripts/panel.py --port 9000

Auth (production):
    BALE_PANEL_TOKEN=...      # cookie signing secret (server-only)
    BALE_PANEL_PASSWORD=...   # operator login password
    BALE_PANEL_USER=admin     # optional login username

    python scripts/panel.py --no-auth                   # local dev only!

On the VPS the service binds 127.0.0.1; nginx exposes HTTPS on the public host.
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
    parser.add_argument(
        "--token",
        default="",
        help="cookie signing secret (or BALE_PANEL_TOKEN)",
    )
    parser.add_argument(
        "--password",
        default="",
        help="operator login password (or BALE_PANEL_PASSWORD)",
    )
    parser.add_argument(
        "--username",
        default="",
        help="login username (or BALE_PANEL_USER, default admin)",
    )
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
    password = args.password or os.getenv("BALE_PANEL_PASSWORD", "")
    username = args.username or os.getenv("BALE_PANEL_USER", panel_auth.DEFAULT_PANEL_USER)
    generated_secret = False
    if not token:
        token = panel_auth.generate_token()
        generated_secret = True

    if not args.no_auth:
        if not panel_auth.token_ok(token):
            print(
                f"[err] BALE_PANEL_TOKEN too short ({len(token)} chars) — need >= "
                f"{panel_auth.MIN_TOKEN_LENGTH}",
                file=sys.stderr,
            )
            return 2
        if not panel_auth.password_ok(password):
            print(
                f"[err] set BALE_PANEL_PASSWORD (>= {panel_auth.MIN_PASSWORD_LENGTH} chars) "
                "or use --no-auth for local dev only",
                file=sys.stderr,
            )
            return 2

    print("=" * 56)
    print("PlayTalk Bale admin panel")
    print(f"  url:    http://{args.host}:{args.port}")
    if args.no_auth:
        print("  auth:   DISABLED (--no-auth) — local development only")
    else:
        print(f"  user:   {username}")
        print("  login:  BALE_PANEL_PASSWORD (not printed)")
        if generated_secret:
            print(f"  secret: generated BALE_PANEL_TOKEN={token}")
            print("          (pin this in .env.secrets on the VPS)")
    print("=" * 56)

    app = build_app(
        token=token,
        password=password,
        username=username,
        no_auth=args.no_auth,
        dialog_limit=args.dialog_limit,
    )
    web.run_app(app, host=args.host, port=args.port, print=lambda *_: None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
