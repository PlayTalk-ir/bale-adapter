"""Persistent API bearer tokens (panel-managed + env fallback)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ulid import ULID

from bale_platform import panel_auth

STORE_VERSION = 1
DEFAULT_PATH = Path("data/api_tokens.json")


def tokens_path() -> Path:
    return Path(os.getenv("BALE_API_TOKENS_PATH", str(DEFAULT_PATH)))


@dataclass
class ApiTokenRecord:
    id: str
    label: str
    secret_sha256: str
    prefix: str
    created_at: float

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "secret_sha256": self.secret_sha256,
            "prefix": self.prefix,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, raw: dict) -> "ApiTokenRecord":
        return cls(
            id=str(raw["id"]),
            label=str(raw.get("label") or ""),
            secret_sha256=str(raw["secret_sha256"]),
            prefix=str(raw.get("prefix") or ""),
            created_at=float(raw.get("created_at") or 0),
        )


def _hash_secret(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_raw(path: Path) -> dict:
    if not path.is_file():
        return {"version": STORE_VERSION, "tokens": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": STORE_VERSION, "tokens": []}
    if not isinstance(data, dict):
        return {"version": STORE_VERSION, "tokens": []}
    return data


def _save_raw(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def list_records(path: Optional[Path] = None) -> List[ApiTokenRecord]:
    p = path or tokens_path()
    data = _load_raw(p)
    tokens = data.get("tokens") or []
    out: List[ApiTokenRecord] = []
    for item in tokens:
        if isinstance(item, dict) and item.get("id") and item.get("secret_sha256"):
            out.append(ApiTokenRecord.from_json(item))
    out.sort(key=lambda r: r.created_at, reverse=True)
    return out


def has_stored_tokens(path: Optional[Path] = None) -> bool:
    return bool(list_records(path))


def env_plaintext_tokens() -> List[str]:
    raw = os.getenv("BALE_ADAPTER_API_TOKENS", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


def api_auth_configured(path: Optional[Path] = None) -> bool:
    return bool(env_plaintext_tokens()) or has_stored_tokens(path)


def verification_sets(path: Optional[Path] = None) -> Tuple[List[str], List[str]]:
    """Return (plaintext_tokens, sha256_hex_hashes) for Bearer validation."""
    plain = env_plaintext_tokens()
    hashes = [r.secret_sha256 for r in list_records(path)]
    return plain, hashes


def create_token(*, label: str = "", path: Optional[Path] = None) -> Tuple[str, ApiTokenRecord]:
    p = path or tokens_path()
    plain = panel_auth.generate_token(40)
    record = ApiTokenRecord(
        id=str(ULID()),
        label=(label or "").strip()[:120],
        secret_sha256=_hash_secret(plain),
        prefix=plain[:8],
        created_at=time.time(),
    )
    data = _load_raw(p)
    tokens = data.get("tokens")
    if not isinstance(tokens, list):
        tokens = []
    tokens.append(record.to_json())
    data["version"] = STORE_VERSION
    data["tokens"] = tokens
    _save_raw(p, data)
    return plain, record


def revoke_token(token_id: str, *, path: Optional[Path] = None) -> bool:
    p = path or tokens_path()
    data = _load_raw(p)
    tokens = data.get("tokens")
    if not isinstance(tokens, list):
        return False
    kept = [t for t in tokens if not (isinstance(t, dict) and str(t.get("id")) == str(token_id))]
    if len(kept) == len(tokens):
        return False
    data["tokens"] = kept
    _save_raw(p, data)
    return True
