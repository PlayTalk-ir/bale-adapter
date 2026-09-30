"""SQLite outbox for API-queued Bale messages (WAL)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TERMINAL_STATUSES = frozenset(
    {"sent", "failed", "expired", "cancelled", "delivery_unknown"}
)
ACTIVE_STATUSES = frozenset({"queued", "resolving", "sending"})


class OutboxStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _tx(self):
        try:
            yield
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                payload_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                text TEXT NOT NULL,
                meta_json TEXT,
                recipient_type TEXT,
                recipient_masked TEXT,
                recipient_secret TEXT,
                bale_user_id INTEGER,
                bale_message_id INTEGER,
                error_code TEXT,
                error_message TEXT,
                dry_run INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL DEFAULT 0,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL,
                sent_at REAL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_status_next
                ON messages(status, next_attempt_at);

            CREATE TABLE IF NOT EXISTS peer_cache (
                cache_key TEXT PRIMARY KEY,
                miss INTEGER NOT NULL,
                bale_user_id INTEGER,
                error_code TEXT,
                expires_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS send_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                key TEXT NOT NULL,
                ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ledger_kind_key_ts
                ON send_ledger(kind, key, ts);

            CREATE TABLE IF NOT EXISTS intake_rate (
                token_hash TEXT NOT NULL,
                minute_bucket INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (token_hash, minute_bucket)
            );

            CREATE TABLE IF NOT EXISTS lookup_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_lookup_at REAL NOT NULL DEFAULT 0,
                day_bucket INTEGER NOT NULL DEFAULT 0,
                day_count INTEGER NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO lookup_state (id, last_lookup_at, day_bucket, day_count)
                VALUES (1, 0, 0, 0);

            CREATE TABLE IF NOT EXISTS api_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                consecutive_errors INTEGER NOT NULL DEFAULT 0,
                breaker_open INTEGER NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO api_state (id, consecutive_errors, breaker_open)
                VALUES (1, 0, 0);
            """
        )
        self._conn.commit()

    @staticmethod
    def payload_hash(recipient_norm: str, text: str) -> str:
        return hashlib.sha256(f"{recipient_norm}\0{text}".encode()).hexdigest()

    def queue_depth(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE status IN ('queued','resolving','sending')"
        ).fetchone()
        return int(row["c"])

    def intake_allowed(
        self,
        token: str,
        rate_per_min: int,
        queue_max: int,
        slots: int = 1,
    ) -> Tuple[bool, Optional[int]]:
        slots = max(1, int(slots))
        if self.queue_depth() + slots > queue_max:
            return False, 60
        th = hashlib.sha256(token.encode()).hexdigest()[:16]
        bucket = int(time.time() // 60)
        with self._tx():
            row = self._conn.execute(
                "SELECT count FROM intake_rate WHERE token_hash=? AND minute_bucket=?",
                (th, bucket),
            ).fetchone()
            count = int(row["count"]) if row else 0
            if count + slots > rate_per_min:
                return False, 60 - int(time.time() % 60) or 1
            if row:
                self._conn.execute(
                    "UPDATE intake_rate SET count=count+? WHERE token_hash=? AND minute_bucket=?",
                    (slots, th, bucket),
                )
            else:
                self._conn.execute(
                    "INSERT INTO intake_rate (token_hash, minute_bucket, count) VALUES (?,?,?)",
                    (th, bucket, slots),
                )
        return True, None

    def insert_message(
        self,
        *,
        message_id: str,
        idempotency_key: str,
        payload_hash: str,
        text: str,
        meta: Optional[dict],
        recipient_type: str,
        recipient_masked: str,
        recipient_secret: str,
        expires_at: float,
        now: float,
    ) -> None:
        with self._tx():
            self._conn.execute(
                """
                INSERT INTO messages (
                    message_id, idempotency_key, payload_hash, status, text, meta_json,
                    recipient_type, recipient_masked, recipient_secret,
                    expires_at, created_at, updated_at, next_attempt_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    message_id,
                    idempotency_key,
                    payload_hash,
                    "queued",
                    text,
                    json.dumps(meta) if meta else None,
                    recipient_type,
                    recipient_masked,
                    recipient_secret,
                    expires_at,
                    now,
                    now,
                    now,
                ),
            )

    def get_by_idempotency(self, key: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM messages WHERE idempotency_key=?", (key,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_message_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM messages WHERE message_id=?", (message_id,)
        ).fetchone()
        return dict(row) if row else None

    def claim_next(self, now: float) -> Optional[Dict[str, Any]]:
        with self._tx():
            row = self._conn.execute(
                """
                SELECT message_id FROM messages
                WHERE status='queued' AND next_attempt_at <= ? AND expires_at > ?
                ORDER BY created_at LIMIT 1
                """,
                (now, now),
            ).fetchone()
            if not row:
                return None
            mid = row["message_id"]
            cur = self._conn.execute(
                """
                UPDATE messages SET status='resolving', updated_at=?
                WHERE message_id=? AND status='queued'
                """,
                (now, mid),
            )
            if cur.rowcount != 1:
                return None
        return self.get_by_message_id(mid)

    def update_row(self, message_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [message_id]
        with self._tx():
            self._conn.execute(f"UPDATE messages SET {cols} WHERE message_id=?", vals)

    def mark_sending(self, message_id: str, now: float) -> None:
        self.update_row(message_id, status="sending", updated_at=now)

    def finalize_terminal(self, message_id: str, **fields: Any) -> None:
        fields.setdefault("recipient_secret", None)
        self.update_row(message_id, **fields)

    def recover_stuck_sending(self) -> int:
        now = time.time()
        with self._tx():
            cur = self._conn.execute(
                """
                UPDATE messages SET status='delivery_unknown', error_code='delivery_unknown',
                    error_message='interrupted while sending', updated_at=?,
                    recipient_secret=NULL
                WHERE status='sending'
                """,
                (now,),
            )
            return cur.rowcount

    def expire_due(self, now: float) -> int:
        with self._tx():
            cur = self._conn.execute(
                """
                UPDATE messages SET status='expired', error_code='expired',
                    error_message='TTL exceeded', updated_at=?, recipient_secret=NULL
                WHERE status IN ('queued','resolving') AND expires_at <= ?
                """,
                (now, now),
            )
            return cur.rowcount

    def get_peer_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM peer_cache WHERE cache_key=? AND expires_at > ?",
            (cache_key, time.time()),
        ).fetchone()
        if not row:
            return None
        return {
            "miss": bool(row["miss"]),
            "bale_user_id": row["bale_user_id"],
            "error_code": row["error_code"],
        }

    def set_peer_cache(
        self,
        cache_key: str,
        *,
        miss: bool,
        bale_user_id: Optional[int] = None,
        error_code: Optional[str] = None,
        ttl_seconds: int = 86400,
    ) -> None:
        exp = time.time() + ttl_seconds
        with self._tx():
            self._conn.execute(
                """
                INSERT INTO peer_cache (cache_key, miss, bale_user_id, error_code, expires_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    miss=excluded.miss, bale_user_id=excluded.bale_user_id,
                    error_code=excluded.error_code, expires_at=excluded.expires_at
                """,
                (cache_key, int(miss), bale_user_id, error_code, exp),
            )

    def try_acquire_lookup_slot(self, min_interval: float, now: float) -> bool:
        with self._tx():
            row = self._conn.execute("SELECT last_lookup_at FROM lookup_state WHERE id=1").fetchone()
            last = float(row["last_lookup_at"])
            if now - last < min_interval:
                return False
            self._conn.execute(
                "UPDATE lookup_state SET last_lookup_at=? WHERE id=1", (now,)
            )
            return True

    def can_new_peer_lookup(self, max_per_day: int, now: float) -> bool:
        day = int(now // 86400)
        with self._tx():
            row = self._conn.execute(
                "SELECT day_bucket, day_count FROM lookup_state WHERE id=1"
            ).fetchone()
            if int(row["day_bucket"]) != day:
                self._conn.execute(
                    "UPDATE lookup_state SET day_bucket=?, day_count=0 WHERE id=1", (day,)
                )
                return True
            return int(row["day_count"]) < max_per_day

    def record_new_peer_lookup(self, now: float) -> None:
        day = int(now // 86400)
        with self._tx():
            row = self._conn.execute(
                "SELECT day_bucket, day_count FROM lookup_state WHERE id=1"
            ).fetchone()
            if int(row["day_bucket"]) != day:
                self._conn.execute(
                    "UPDATE lookup_state SET day_bucket=?, day_count=1 WHERE id=1", (day,)
                )
            else:
                self._conn.execute(
                    "UPDATE lookup_state SET day_count=day_count+1 WHERE id=1"
                )

    def record_send(self, kind: str, key: str, ts: float) -> None:
        with self._tx():
            self._conn.execute(
                "INSERT INTO send_ledger (kind, key, ts) VALUES (?,?,?)", (kind, key, ts)
            )

    def count_sends(self, kind: str, key: str, since: float) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM send_ledger WHERE kind=? AND key=? AND ts>=?",
            (kind, key, since),
        ).fetchone()
        return int(row["c"])

    def last_send_ts(self, kind: str, key: str) -> Optional[float]:
        row = self._conn.execute(
            "SELECT MAX(ts) AS m FROM send_ledger WHERE kind=? AND key=?",
            (kind, key),
        ).fetchone()
        m = row["m"]
        return float(m) if m is not None else None

    def breaker_open(self) -> bool:
        row = self._conn.execute(
            "SELECT breaker_open FROM api_state WHERE id=1"
        ).fetchone()
        return bool(row["breaker_open"])

    def record_bale_error(self, is_session: bool, threshold: int) -> None:
        with self._tx():
            if is_session:
                self._conn.execute(
                    "UPDATE api_state SET consecutive_errors=?, breaker_open=1 WHERE id=1",
                    (threshold,),
                )
                return
            self._conn.execute(
                "UPDATE api_state SET consecutive_errors=consecutive_errors+1 WHERE id=1"
            )
            row = self._conn.execute(
                "SELECT consecutive_errors FROM api_state WHERE id=1"
            ).fetchone()
            if int(row["consecutive_errors"]) >= threshold:
                self._conn.execute("UPDATE api_state SET breaker_open=1 WHERE id=1")

    def record_bale_success(self) -> None:
        with self._tx():
            self._conn.execute(
                "UPDATE api_state SET consecutive_errors=0 WHERE id=1"
            )

    def resume_breaker(self) -> None:
        with self._tx():
            self._conn.execute(
                "UPDATE api_state SET breaker_open=0, consecutive_errors=0 WHERE id=1"
            )
