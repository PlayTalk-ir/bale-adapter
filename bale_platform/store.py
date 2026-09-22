"""SQLite store for support-agent inbox tracking.

Bale's unread_count is account-wide (one shared login). To answer "what is
unread for agent Sara?" we track which customer messages each agent has acked.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "support_inbox.sqlite"


@dataclass
class StoredMessage:
    chat_id: str
    message_id: int
    sender_id: str
    text: str
    timestamp: str
    date_ms: int
    direction: str  # "in" | "out"


class SupportStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_STORE_PATH
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
                CREATE TABLE IF NOT EXISTS messages (
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    sender_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    date_ms INTEGER NOT NULL,
                    direction TEXT NOT NULL DEFAULT 'in',
                    PRIMARY KEY (chat_id, message_id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_chat_date
                    ON messages(chat_id, date_ms DESC);

                CREATE TABLE IF NOT EXISTS agent_acks (
                    agent_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    last_message_id INTEGER NOT NULL,
                    acked_at TEXT NOT NULL,
                    PRIMARY KEY (agent_id, chat_id)
                );

                CREATE TABLE IF NOT EXISTS chat_labels (
                    chat_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    category TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def upsert_message(self, msg: Dict[str, Any], *, direction: str = "in") -> None:
        chat_id = str(msg.get("chat_id") or "")
        message_id = msg.get("message_id")
        if not chat_id or message_id is None:
            return
        text = (msg.get("text") or "").strip()
        if not text:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO messages
                    (chat_id, message_id, sender_id, text, timestamp, date_ms, direction)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    int(message_id),
                    str(msg.get("sender_id") or ""),
                    text,
                    str(msg.get("timestamp") or ""),
                    int(msg.get("date_ms") or 0),
                    direction,
                ),
            )

    def ack_chat(self, agent_id: str, chat_id: str, last_message_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_acks
                    (agent_id, chat_id, last_message_id, acked_at)
                VALUES (?, ?, ?, ?)
                """,
                (agent_id, chat_id, last_message_id, now),
            )

    def get_last_ack(self, agent_id: str, chat_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_message_id FROM agent_acks WHERE agent_id=? AND chat_id=?",
                (agent_id, chat_id),
            ).fetchone()
        return int(row["last_message_id"]) if row else 0

    def unread_for_agent(
        self, agent_id: str, *, account_user_id: Optional[str] = None
    ) -> List[StoredMessage]:
        """Customer messages newer than this agent's last ack on each chat."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.*
                FROM messages m
                LEFT JOIN agent_acks a
                    ON a.agent_id = ? AND a.chat_id = m.chat_id
                WHERE m.direction = 'in'
                  AND m.message_id > COALESCE(a.last_message_id, 0)
                ORDER BY m.date_ms DESC
                """,
                (agent_id,),
            ).fetchall()
        out: List[StoredMessage] = []
        for row in rows:
            if account_user_id and str(row["sender_id"]) == account_user_id:
                continue
            out.append(
                StoredMessage(
                    chat_id=row["chat_id"],
                    message_id=row["message_id"],
                    sender_id=row["sender_id"],
                    text=row["text"],
                    timestamp=row["timestamp"],
                    date_ms=row["date_ms"],
                    direction=row["direction"],
                )
            )
        return out

    def recent_messages(
        self, *, chat_id: Optional[str] = None, limit: int = 200, since_ms: int = 0
    ) -> List[StoredMessage]:
        query = """
            SELECT * FROM messages
            WHERE date_ms >= ?
        """
        params: List[Any] = [since_ms]
        if chat_id:
            query += " AND chat_id = ?"
            params.append(chat_id)
        query += " ORDER BY date_ms DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            StoredMessage(
                chat_id=r["chat_id"],
                message_id=r["message_id"],
                sender_id=r["sender_id"],
                text=r["text"],
                timestamp=r["timestamp"],
                date_ms=r["date_ms"],
                direction=r["direction"],
            )
            for r in rows
        ]

    def latest_incoming_per_chat(self) -> Dict[str, StoredMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.*
                FROM messages m
                INNER JOIN (
                    SELECT chat_id, MAX(message_id) AS max_id
                    FROM messages
                    WHERE direction = 'in'
                    GROUP BY chat_id
                ) t ON m.chat_id = t.chat_id AND m.message_id = t.max_id
                """
            ).fetchall()
        return {
            r["chat_id"]: StoredMessage(
                chat_id=r["chat_id"],
                message_id=r["message_id"],
                sender_id=r["sender_id"],
                text=r["text"],
                timestamp=r["timestamp"],
                date_ms=r["date_ms"],
                direction=r["direction"],
            )
            for r in rows
        }
