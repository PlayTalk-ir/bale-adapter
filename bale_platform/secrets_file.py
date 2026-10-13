"""Read/update `.env.secrets` lines (API tokens) without loading secrets into git."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

TOKEN_KEY = "BALE_ADAPTER_API_TOKENS"
_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_token_cache: Optional[Tuple[float, List[str]]] = None


def secrets_path() -> Path:
    raw = os.getenv("BALE_SECRETS_FILE", ".env.secrets")
    return Path(raw).expanduser()


def mask_token(token: str) -> str:
    token = token.strip()
    if len(token) <= 10:
        return "****"
    return f"{token[:6]}…{token[-4:]}"


def parse_tokens_value(raw: str) -> List[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def read_api_tokens(path: Path | None = None) -> List[str]:
    """Tokens from the secrets file when present; else ``BALE_ADAPTER_API_TOKENS`` env."""
    path = path or secrets_path()
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = _LINE.match(line)
            if match and match.group(1) == TOKEN_KEY:
                return parse_tokens_value(match.group(2))
    return parse_tokens_value(os.getenv(TOKEN_KEY, ""))


def invalidate_token_cache() -> None:
    global _token_cache
    _token_cache = None


def active_api_tokens(*, force: bool = False) -> List[str]:
    """Bearer tokens for API auth; reloads when ``.env.secrets`` changes (no service restart)."""
    global _token_cache
    path = secrets_path()
    try:
        mtime = path.stat().st_mtime if path.is_file() else 0.0
    except OSError:
        mtime = 0.0
    if not force and _token_cache is not None and _token_cache[0] == mtime:
        return list(_token_cache[1])
    tokens = read_api_tokens(path)
    _token_cache = (mtime, tokens)
    return list(tokens)


def append_api_token(new_token: str, path: Path | None = None) -> None:
    """Append one bearer token to BALE_ADAPTER_API_TOKENS in the secrets file."""
    new_token = new_token.strip()
    if len(new_token) < 16:
        raise ValueError("token too short")
    path = path or secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    updated = False
    out: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            out.append(line)
            continue
        match = _LINE.match(stripped)
        if match and match.group(1) == TOKEN_KEY:
            existing = parse_tokens_value(match.group(2))
            if new_token in existing:
                return
            merged = ",".join(existing + [new_token])
            out.append(f"{TOKEN_KEY}={merged}")
            updated = True
        else:
            out.append(line)
    if not updated:
        out.append(f"{TOKEN_KEY}={new_token}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    invalidate_token_cache()
