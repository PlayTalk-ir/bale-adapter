"""Request validation for POST /v1/messages."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Optional, Tuple

from bale_platform.phone import mask_phone, try_normalize_iranian_mobile

_IDEM_RE = re.compile(r"^[A-Za-z0-9:_.-]{1,128}$")
MAX_RECIPIENTS_PER_REQUEST = 50


def validate_idempotency_key(key: str) -> bool:
    return bool(_IDEM_RE.match(key))


def derive_idempotency_key(base: str, norm_key: str) -> str:
    """Stable per-recipient key when a request targets multiple recipients."""
    suffix = norm_key.replace(":", "_")
    candidate = f"{base}:{suffix}"
    if len(candidate) <= 128 and validate_idempotency_key(candidate):
        return candidate
    digest = hashlib.sha256(norm_key.encode()).hexdigest()[:24]
    trimmed = base[: max(1, 128 - 25)]
    candidate = f"{trimmed}:{digest}"
    if validate_idempotency_key(candidate):
        return candidate
    return f"{digest}:{hashlib.sha256(base.encode()).hexdigest()[:24]}"[:128]


def parse_recipient_dict(rec: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not isinstance(rec, dict):
        return None, "recipient_invalid"
    keys = [k for k in ("phone", "bale_user_id", "username") if k in rec and rec[k] not in (None, "")]
    if len(keys) != 1:
        return None, "recipient_invalid"
    kind = keys[0]
    if kind == "phone":
        phone = str(rec["phone"]).strip()
        norm = try_normalize_iranian_mobile(phone)
        if not norm:
            return None, "recipient_invalid"
        return {
            "type": "phone",
            "phone": norm,
            "masked": mask_phone(norm),
            "norm_key": f"phone:{norm}",
            "secret": {"type": "phone", "phone": norm},
        }, None
    if kind == "bale_user_id":
        uid = str(rec["bale_user_id"]).strip()
        if not uid.isdigit():
            return None, "recipient_invalid"
        return {
            "type": "bale_user_id",
            "masked": uid,
            "norm_key": f"uid:{uid}",
            "secret": {"type": "bale_user_id", "bale_user_id": uid},
        }, None
    username = str(rec["username"]).strip().lstrip("@")
    if not username:
        return None, "recipient_invalid"
    return {
        "type": "username",
        "masked": f"@{username[:2]}***" if len(username) > 2 else "@***",
        "norm_key": f"user:{username.lower()}",
        "secret": {"type": "username", "username": username},
    }, None


def parse_recipients(body: dict) -> Tuple[Optional[list], Optional[str]]:
    has_single = "recipient" in body and body.get("recipient") is not None
    has_multi = "recipients" in body and body.get("recipients") is not None
    if has_single and has_multi:
        return None, "recipient_invalid"
    if not has_single and not has_multi:
        return None, "recipient_invalid"
    if has_single:
        rec, err = parse_recipient_dict(body.get("recipient"))
        if err:
            return None, err
        return [rec], None
    raw = body.get("recipients")
    if not isinstance(raw, list) or len(raw) < 1:
        return None, "recipient_invalid"
    if len(raw) > MAX_RECIPIENTS_PER_REQUEST:
        return None, "recipient_invalid"
    parsed: list = []
    seen_norm: set[str] = set()
    for item in raw:
        rec, err = parse_recipient_dict(item)
        if err:
            return None, err
        if rec["norm_key"] in seen_norm:
            return None, "recipient_invalid"
        seen_norm.add(rec["norm_key"])
        parsed.append(rec)
    return parsed, None


def validate_post_body(body: dict, default_ttl: int, max_ttl: int) -> Tuple[Optional[dict], Optional[dict]]:
    """Return (normalized, error_dict) where error_dict is API error shape."""
    text = body.get("text")
    if not isinstance(text, str) or len(text) < 1:
        return None, _err("recipient_invalid", "text is required", {})
    if len(text) > 4000:
        return None, _err("text_too_long", "text exceeds 4000 characters", {}, status=413)
    key = body.get("idempotency_key")
    if not isinstance(key, str) or not validate_idempotency_key(key):
        return None, _err("recipient_invalid", "invalid idempotency_key", {})
    recipients, rerr = parse_recipients(body)
    if rerr:
        return None, _err(rerr, "invalid recipient", {})
    meta = body.get("meta")
    if meta is not None:
        if not isinstance(meta, dict):
            return None, _err("recipient_invalid", "meta must be an object", {})
        if len(json.dumps(meta, ensure_ascii=False)) > 2048:
            return None, _err("recipient_invalid", "meta exceeds 2KB", {})
    ttl = body.get("ttl_seconds", default_ttl)
    if ttl is None:
        ttl = default_ttl
    try:
        ttl = int(ttl)
    except (TypeError, ValueError):
        return None, _err("recipient_invalid", "invalid ttl_seconds", {})
    if ttl < 1 or ttl > max_ttl:
        return None, _err("recipient_invalid", "ttl_seconds out of range", {})
    multi = "recipients" in body and body.get("recipients") is not None
    items = []
    for rec in recipients:
        if multi:
            idem = derive_idempotency_key(key, rec["norm_key"])
        else:
            idem = key
        items.append(
            {
                "recipient": rec,
                "idempotency_key": idem,
                "payload_hash_input": f"{rec['norm_key']}\0{text}",
            }
        )
    return {
        "text": text,
        "idempotency_key": key,
        "meta": meta,
        "ttl_seconds": ttl,
        "multi": multi,
        "items": items,
    }, None


def _err(code: str, message: str, details: dict, status: int = 422) -> dict:
    return {"status": status, "error": {"code": code, "message": message, "details": details}}
