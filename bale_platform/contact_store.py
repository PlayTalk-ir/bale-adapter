"""Persistent local contact book: names → Bale chat ids.

Why a local book at all?

* Bale's own address book (``load_contacts``) is empty for the company account,
  so the names we can resolve come from dialogs.
* Support staff also serve people they have **never** chatted with. Those are
  added by hand and must survive every refresh.

Storage: SQLite at ``data/contacts.sqlite`` (override ``BALE_CONTACTS_PATH``).

Refresh policy (:func:`refresh_book`):

* Bale rows update ``local_name`` / ``profile_name`` / ``username`` / ``source``.
* ``name`` is only overwritten for rows that were **not** set by a human.
* Manual rows are never deleted (`prune` only drops stale non-manual rows).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bale_platform.contacts import (
    ContactIndex,
    SavedContact,
    build_contact_index,
    normalize_name,
)

DEFAULT_CONTACTS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "contacts.sqlite"
)

SOURCE_MANUAL = "manual"


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class BookEntry:
    """One row of the local contact book."""

    chat_id: int
    name: str
    local_name: str = ""
    profile_name: str = ""
    username: str = ""
    source: str = SOURCE_MANUAL
    manual: bool = False
    updated_at: str = ""

    def to_contact(self) -> SavedContact:
        return SavedContact(
            chat_id=self.chat_id,
            name=self.name,
            source=self.source,
            local_name=self.local_name,
            profile_name=self.profile_name,
            username=self.username,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "name": self.name,
            "local_name": self.local_name,
            "profile_name": self.profile_name,
            "username": self.username,
            "source": self.source,
            "manual": self.manual,
            "updated_at": self.updated_at,
        }


class ContactBook:
    """SQLite-backed address book that survives refreshes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_CONTACTS_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    chat_id      INTEGER PRIMARY KEY,
                    name         TEXT NOT NULL,
                    local_name   TEXT NOT NULL DEFAULT '',
                    profile_name TEXT NOT NULL DEFAULT '',
                    username     TEXT NOT NULL DEFAULT '',
                    source       TEXT NOT NULL DEFAULT 'manual',
                    manual       INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name);
                """
            )

    def __len__(self) -> int:
        return self.count()

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM contacts").fetchone()
        return int(row["n"]) if row else 0

    def _row_to_entry(self, row: sqlite3.Row) -> BookEntry:
        return BookEntry(
            chat_id=int(row["chat_id"]),
            name=row["name"],
            local_name=row["local_name"],
            profile_name=row["profile_name"],
            username=row["username"],
            source=row["source"],
            manual=bool(row["manual"]),
            updated_at=row["updated_at"],
        )

    def get(self, chat_id: Any) -> Optional[BookEntry]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM contacts WHERE chat_id = ?", (int(chat_id),)
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def all(self) -> List[BookEntry]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM contacts ORDER BY name").fetchall()
        return [self._row_to_entry(r) for r in rows]

    def search(self, query: str, *, limit: int = 0) -> List[BookEntry]:
        """Persian-friendly fuzzy filter (never raises)."""
        needle = normalize_name(query)
        if not needle:
            entries = self.all()
        else:
            compact = needle.replace(" ", "")
            hits: List[BookEntry] = []
            for entry in self.all():
                contact = entry.to_contact()
                if any(needle in key for key in contact.keys) or any(
                    compact in key for key in contact.compact_keys
                ):
                    hits.append(entry)
            hits.sort(
                key=lambda e: (not e.to_contact().compact.startswith(compact), e.name)
            )
            entries = hits
        return entries[:limit] if limit > 0 else entries

    def to_index(self) -> ContactIndex:
        return ContactIndex(entry.to_contact() for entry in self.all())

    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------

    def upsert_bale(self, contact: SavedContact) -> str:
        """Merge one Bale-sourced contact. Returns ``added``/``updated``/``kept``."""
        now = _now()
        existing = self.get(contact.chat_id)
        if existing is None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO contacts
                        (chat_id, name, local_name, profile_name, username,
                         source, manual, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        contact.chat_id,
                        contact.name,
                        contact.local_name,
                        contact.profile_name,
                        contact.username,
                        contact.source,
                        now,
                        now,
                    ),
                )
            return "added"

        if existing.manual:
            # A human owns the name: refresh the Bale fields only.
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE contacts
                       SET local_name = ?, profile_name = ?, username = ?,
                           updated_at = ?
                     WHERE chat_id = ?
                    """,
                    (
                        contact.local_name or existing.local_name,
                        contact.profile_name or existing.profile_name,
                        contact.username or existing.username,
                        now,
                        contact.chat_id,
                    ),
                )
            return "kept"

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE contacts
                   SET name = ?, local_name = ?, profile_name = ?, username = ?,
                       source = ?, updated_at = ?
                 WHERE chat_id = ?
                """,
                (
                    contact.name,
                    contact.local_name,
                    contact.profile_name,
                    contact.username,
                    contact.source,
                    now,
                    contact.chat_id,
                ),
            )
        return "updated"

    def add_manual(
        self,
        name: str,
        chat_id: int,
        *,
        local_name: str = "",
        profile_name: str = "",
        username: str = "",
    ) -> BookEntry:
        """Add (or re-own) an entry a human typed. Marks it ``manual``."""
        clean = str(name or "").strip() or str(chat_id)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO contacts
                    (chat_id, name, local_name, profile_name, username,
                     source, manual, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    name = excluded.name,
                    source = excluded.source,
                    manual = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    int(chat_id),
                    clean,
                    local_name,
                    profile_name,
                    username,
                    SOURCE_MANUAL,
                    now,
                    now,
                ),
            )
        entry = self.get(chat_id)
        assert entry is not None
        return entry

    def remove(self, chat_id: Any) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM contacts WHERE chat_id = ?", (int(chat_id),)
            )
        return cur.rowcount > 0

    def prune(self, keep_chat_ids: Any) -> int:
        """Delete non-manual rows that Bale no longer reports."""
        keep = {int(cid) for cid in keep_chat_ids}
        removed = 0
        for entry in self.all():
            if entry.manual or entry.chat_id in keep:
                continue
            if self.remove(entry.chat_id):
                removed += 1
        return removed

    def stats(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in self.all():
            key = SOURCE_MANUAL if entry.manual else entry.source
            counts[key] = counts.get(key, 0) + 1
        return counts


async def refresh_book(
    book: ContactBook,
    client: Any,
    *,
    dialog_limit: int = 200,
    chunk_size: int = 50,
    prune: bool = False,
) -> Dict[str, Any]:
    """Pour Bale's address book (+ dialogs) into the local contact book."""
    index = await build_contact_index(
        client,
        include_dialogs=dialog_limit > 0,
        dialog_limit=dialog_limit,
        chunk_size=chunk_size,
    )

    counts: Dict[str, Any] = {
        "found": len(index),
        "added": 0,
        "updated": 0,
        "kept": 0,
        "pruned": 0,
        "notes": list(index.notes),
    }
    for contact in index:
        action = book.upsert_bale(contact)
        counts[action] = int(counts[action]) + 1

    if prune:
        counts["pruned"] = book.prune(c.chat_id for c in index)

    counts["total"] = book.count()
    return counts
