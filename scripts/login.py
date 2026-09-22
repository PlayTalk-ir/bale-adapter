#!/usr/bin/env python3
"""
scripts/login.py — interactive one-time Bale login.

Run on the VPS CONSOLE (SSH in first). NEVER paste the OTP into a chat.

    ssh root@130.185.76.124
    cd /opt/bale-adapter
    source venv/bin/activate
    python scripts/login.py

Flow (uses aiobale's PhoneLoginCLI under the hood, with our own prompt that
respects mode=observe-only and makes the WARNING explicit):
    1. We prompt for phone number (e.g. +989121234567 or 98XXXXXXXXXX)
    2. We call client.start_phone_auth(phone)
    3. Bale sends an OTP to that phone
    4. We prompt for OTP — you type it at the terminal
    5. We call client.validate_code(code, transaction_hash)
    6. aiobale's Client writes the opaque protobuf session to SESSION_PATH
       (it forces suffix `.bale` so we use /opt/bale-adapter/.session/session.bale)
    7. Done. systemd can now restart the runner without re-login.

SECURITY:
    - OTP is read from getpass (no echo to terminal)
    - OTP is NEVER logged, NEVER written to disk by us, NEVER transmitted to Hermes
    - Session file is mode 0700 on the directory, mode 0600 by aiobale
    - The device_hash/device_title passed to start_phone_auth identify this
      login as "hermes-bale-adapter / <vps hostname>" so the Bale device list
      is auditable.
"""

from __future__ import annotations

import asyncio
import getpass
import os
import platform
import sys
from pathlib import Path

# Default session path MUST end in .bale because aiobale's Client.__init__
# does `path.with_suffix(".bale")` and resolves the new path. If you set
# BALE_SESSION_PATH to something without .bale, the actual file will be
# <path>.bale next to it. We default to a clean .bale name.
SESSION_PATH = Path(
    os.getenv("BALE_SESSION_PATH", "/opt/bale-adapter/.session/session.bale")
)


def _ensure_session_dir() -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(SESSION_PATH.parent, 0o700)


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bale_platform.phone import normalize_phone_int as _normalize_phone  # noqa: E402


def _prompt_phone() -> int:
    raw = input("Bale phone number (e.g. +989121234567 or 09XXXXXXXXX): ").strip()
    try:
        return _normalize_phone(raw)
    except ValueError:
        print("[err] invalid phone format — must be digits, optionally prefixed +")
        sys.exit(1)


def _prompt_otp() -> str:
    otp = getpass.getpass("Enter OTP (no echo): ").strip()
    if not otp:
        print("[err] empty OTP — aborting")
        sys.exit(2)
    return otp


async def _login() -> int:
    _ensure_session_dir()

    print("=" * 60)
    print("Bale userbot login (one-time)")
    print("=" * 60)
    print(f"Session file will be: {SESSION_PATH}")
    print(f"Session dir perms:     0700")
    print()
    print("⚠️  WARNING: only use this for the COMPANY PlayTalk Bale account.")
    print("            Do NOT use a personal number — the userbot will read")
    print("            every message in that account's chats.")
    print()

    try:
        from aiobale import Client, Dispatcher  # type: ignore[import-not-found]
    except ImportError:
        print(
            "[err] aiobale is not installed. Run scripts/bootstrap.sh or\n"
            "       source venv/bin/activate && pip install aiobale"
        )
        return 3

    phone = _prompt_phone()
    print(f"[step] phone = {phone}")
    print("[step] Bale will send an OTP to this phone. Type it below when received.")
    print()

    # The dispatcher is required by Client.__init__ but we don't actually
    # listen for messages here — we just want to run start_phone_auth +
    # validate_code. Hand it an empty dispatcher.
    dp = Dispatcher()
    device_title = f"hermes-bale-adapter / {platform.node()}"
    client = Client(dispatcher=dp, session_file=str(SESSION_PATH))

    print(f"[step] device_title = {device_title!r}")
    print(f"[step] calling client.start_phone_auth({phone}) ...")
    resp = await client.start_phone_auth(phone, device_title=device_title)
    if hasattr(resp, "__class__") and resp.__class__.__name__ == "AuthErrors":
        print(f"[err] start_phone_auth returned AuthErrors: {resp}")
        return 4
    if not getattr(resp, "transaction_hash", None):
        print(f"[err] unexpected start_phone_auth response: {resp!r}")
        return 4

    tx_hash = resp.transaction_hash
    if not getattr(resp, "is_registered", True):
        print(
            "[err] this phone is not registered on Bale.\n"
            "       Sign up the company account in the official Bale app first."
        )
        return 5

    expires_ms = getattr(resp.code_expiration_date, "value", 0)
    print(f"[ok] code sent. transaction_hash={tx_hash!r}")
    print(f"     expires at unix-ms = {expires_ms}")
    print()

    otp = _prompt_otp()
    print(f"[step] calling client.validate_code(code, transaction_hash) ...")
    res = await client.validate_code(otp, tx_hash)

    if hasattr(res, "__class__") and res.__class__.__name__ == "AuthErrors":
        print(f"[err] validate_code returned AuthErrors: {res}")
        return 6
    if not getattr(res, "jwt", None) or not getattr(res.jwt, "value", None):
        print(f"[err] unexpected validate_code response: {res!r}")
        return 6

    # aiobale's validate_code already wrote the session to SESSION_PATH.
    # Verify the file is on disk and non-zero, then enforce 0600.
    if not SESSION_PATH.exists() or SESSION_PATH.stat().st_size == 0:
        print(f"[err] validate_code succeeded but session file missing at {SESSION_PATH}")
        return 7
    os.chmod(SESSION_PATH, 0o600)

    user = getattr(res, "user", None)
    if user is not None:
        name = getattr(user, "name", "?")
        uid = getattr(user, "id", "?")
        print(f"[ok] logged in as id={uid} name={name!r}")
    print(f"[ok] session written → {SESSION_PATH}  (mode 0600)")
    print("[done] systemd will pick it up on next start. You can `systemctl restart bale-platform` now.")
    return 0


def main() -> int:
    try:
        return asyncio.run(_login())
    except KeyboardInterrupt:
        print("\n[abort] interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
