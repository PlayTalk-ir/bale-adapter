"""Filter a ``GET /v1/contacts`` payload. The API has no search query."""

from __future__ import annotations

from typing import Any

from bale_platform.contacts import normalize_name


def filter_contacts(
    contacts: list[dict[str, Any]],
    query: str = "",
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Substring match on name, username, phone, and chat id.

    Comparison uses the same folding as the local contact book (Persian
    letters, spacing, digits). Rows are returned as the API sent them.
    """
    key = normalize_name(query)
    if not key:
        hits = list(contacts)
    else:
        compact = key.replace(" ", "")
        hits = [row for row in contacts if _matches(row, key, compact)]
        hits.sort(
            key=lambda row: (
                not normalize_name(row.get("name") or "").replace(" ", "").startswith(compact),
                str(row.get("name") or ""),
            )
        )
    if limit > 0:
        return hits[:limit]
    return hits


def _matches(row: dict[str, Any], key: str, compact: str) -> bool:
    for field in ("name", "username", "phone", "chat_id"):
        folded = normalize_name(row.get(field) or "")
        if not folded:
            continue
        if key in folded or compact in folded.replace(" ", ""):
            return True
    return False
