"""Saved-contact lookup: Persian/local display names → Bale chat ids.

Bale's `unread_count`/chat ids are numeric, but support staff think in names
("نفس پیروز", "امیرحافظ"). This module builds an index of *saved* contacts
(the address book, plus optional dialog partners) and resolves a typed name
to exactly one chat id.

Deliberate design choices:
  * Ambiguous names RAISE (``NameNotUnique``) instead of picking one — the
    adapter must never guess and message the wrong customer.
  * Persian names are folded (Arabic ي/ك, ZWNJ, emoji, decoration, Persian
    digits, spacing) before comparing, so "امیر حافظ سفیدبری" matches the
    saved "امیرحافظ سفیدبری".
  * No top-level aiobale import: this module stays unit-testable in CI where
    the git-only aiobale package is not installed (same trick as adapter.py).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from bale_platform.phone import to_ascii_digits

# aiobale.enums.PeerType.PRIVATE — kept as an int so importing this module
# never requires aiobale (mirrors adapter.py's lazy-import policy).
PEER_TYPE_PRIVATE = 1

#: Characters that are invisible but break naive name equality.
_INVISIBLE = dict.fromkeys(
    map(ord, "\u200b\u200c\u200d\u200e\u200f\u2060\u2069\ufeff"), None
)

#: Arabic/Persian letter variants folded to one canonical Persian letter.
_LETTERS = {
    "ي": "ی",
    "ى": "ی",
    "ﻯ": "ی",
    "ﻰ": "ی",
    "ك": "ک",
    "ﻙ": "ک",
    "ﻻ": "لا",
    "ﻷ": "لا",
    "ة": "ه",
    "ۀ": "ه",
    "ؤ": "و",
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ٱ": "ا",
    "ئ": "ی",
}

#: Anything that is not a letter/digit/space is decoration (emoji, (), •, .).
_DECOR = re.compile(r"[^0-9a-z\u0600-\u06ff\s]+", re.UNICODE)
_WS = re.compile(r"\s+", re.UNICODE)


def normalize_name(raw: Any) -> str:
    """Fold a Bale display name to a stable comparison key.

    >>> normalize_name("• امیر حافظ سفیدبری (خودش) 🥲")
    'امیر حافظ سفیدبری خودش'
    """
    s = unicodedata.normalize("NFKC", to_ascii_digits(str(raw or "")))
    s = s.translate(_INVISIBLE)
    s = "".join(_LETTERS.get(ch, ch) for ch in s)
    s = _DECOR.sub(" ", s.lower())
    return _WS.sub(" ", s).strip()


class NameLookupError(LookupError):
    """Base class for name → contact resolution failures."""


class NameNotFound(NameLookupError):
    """No saved contact matches the query."""


class NameNotUnique(NameLookupError):
    """Several saved contacts match — the caller must disambiguate."""

    def __init__(self, query: str, candidates: Sequence["SavedContact"]) -> None:
        self.query = query
        self.candidates = list(candidates)
        shown = ", ".join(f"{c.chat_id} ({c.name})" for c in self.candidates[:5])
        extra = "" if len(self.candidates) <= 5 else f" +{len(self.candidates) - 5} more"
        super().__init__(
            f"{len(self.candidates)} contacts match {query!r}: {shown}{extra}"
        )


@dataclass
class SavedContact:
    """One resolvable Bale peer: a saved contact or a dialog partner."""

    chat_id: int
    name: str
    source: str = "contacts"  # "contacts" (address book) | "dialog"
    local_name: str = ""
    profile_name: str = ""
    username: str = ""
    is_bot: bool = False
    keys: List[str] = field(default_factory=list, init=False, repr=False)
    compact_keys: List[str] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        variants = [self.name, self.local_name, self.profile_name, self.username]
        keys: List[str] = []
        compacts: List[str] = []
        for variant in variants:
            key = normalize_name(variant)
            if not key:
                continue
            if key not in keys:
                keys.append(key)
            compact = key.replace(" ", "")
            if compact not in compacts:
                compacts.append(compact)
        self.keys = keys
        self.compact_keys = compacts

    @property
    def key(self) -> str:
        return self.keys[0] if self.keys else ""

    @property
    def compact(self) -> str:
        return self.compact_keys[0] if self.compact_keys else ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "name": self.name,
            "local_name": self.local_name,
            "profile_name": self.profile_name,
            "username": self.username,
            "source": self.source,
            "is_bot": self.is_bot,
        }


def _unique(contacts: Iterable[SavedContact]) -> List[SavedContact]:
    """De-duplicate by chat id, keeping first-seen order."""
    seen: set[int] = set()
    out: List[SavedContact] = []
    for c in contacts:
        if c.chat_id in seen:
            continue
        seen.add(c.chat_id)
        out.append(c)
    return out


class ContactIndex:
    """Lookup table for saved contacts: name variants → chat id."""

    def __init__(self, contacts: Iterable[SavedContact] = ()) -> None:
        self.contacts: List[SavedContact] = _unique(contacts)
        #: human-readable lookup diagnostics from build_contact_index()
        self.notes: List[str] = []
        self._by_key: Dict[str, List[SavedContact]] = {}
        self._by_compact: Dict[str, List[SavedContact]] = {}
        for c in self.contacts:
            for key in c.keys:
                self._by_key.setdefault(key, []).append(c)
            for key in c.compact_keys:
                self._by_compact.setdefault(key, []).append(c)

    def __len__(self) -> int:
        return len(self.contacts)

    def __iter__(self):
        return iter(self.contacts)

    def get(self, chat_id: Any) -> Optional[SavedContact]:
        for c in self.contacts:
            if str(c.chat_id) == str(chat_id):
                return c
        return None

    def resolve(self, query: str) -> SavedContact:
        """Return the single contact matching ``query``.

        Raises:
            NameNotFound: nothing matches.
            NameNotUnique: more than one contact matches (never guess!).
        """
        key = normalize_name(query)
        if not key:
            raise NameNotFound("empty name — nothing to match")
        compact = key.replace(" ", "")

        # 1) exact match on any name variant (saved name, profile name, username)
        for pool in (self._by_key.get(key), self._by_compact.get(compact)):
            hits = _unique(pool or [])
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                raise NameNotUnique(query, hits)

        # 2) prefix, then substring — tolerant of spacing differences
        def _prefix(c: SavedContact) -> bool:
            return any(k.startswith(key) for k in c.keys) or any(
                k.startswith(compact) for k in c.compact_keys
            )

        def _partial(c: SavedContact) -> bool:
            return any(key in k for k in c.keys) or any(
                compact in k for k in c.compact_keys
            )

        for matcher in (_prefix, _partial):
            hits = _unique([c for c in self.contacts if matcher(c)])
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                raise NameNotUnique(query, hits)

        raise NameNotFound(f"no saved contact matches {query!r}")

    def search(self, query: str = "", *, limit: int = 0) -> List[SavedContact]:
        """Fuzzy list for `contacts --search` (never raises)."""
        key = normalize_name(query)
        if not key:
            hits = list(self.contacts)
        else:
            compact = key.replace(" ", "")
            hits = [
                c
                for c in self.contacts
                if any(key in k for k in c.keys)
                or any(compact in k for k in c.compact_keys)
            ]
            hits.sort(key=lambda c: (not c.compact.startswith(compact), c.name))
        return hits[:limit] if limit > 0 else hits


def contact_from_user(user: Any, *, source: str = "contacts") -> Optional[SavedContact]:
    """Build a :class:`SavedContact` from an aiobale ``User`` (duck-typed)."""
    chat_id = int(getattr(user, "id", 0) or 0)
    if chat_id <= 0:
        return None
    local_name = str(getattr(user, "local_name", "") or "").strip()
    profile_name = str(getattr(user, "name", "") or "").strip()
    username = getattr(user, "username", "") or ""
    # Some aiobale versions wrap username in StringValue (.value)
    username = str(getattr(username, "value", username) or "").strip()
    return SavedContact(
        chat_id=chat_id,
        name=local_name or profile_name or username or str(chat_id),
        source=source,
        local_name=local_name,
        profile_name=profile_name,
        username=username.lstrip("@"),
        is_bot=bool(getattr(user, "is_bot", False)),
    )


def peer_chat_id(peer: Any) -> int:
    return int(getattr(peer, "id", 0) or 0)


def peer_is_private(peer: Any) -> bool:
    """True for 1-on-1 peers. Works with aiobale PeerType or a plain int."""
    raw = getattr(peer, "type", None)
    value = getattr(raw, "value", raw)
    try:
        return int(value) == PEER_TYPE_PRIVATE
    except (TypeError, ValueError):
        return False


def _private_chat_type() -> Any:
    """aiobale ``ChatType.PRIVATE`` — imported lazily (git-only dependency)."""
    from aiobale.enums import ChatType  # type: ignore[import-untyped]

    return ChatType.PRIVATE


def _merge_contact(
    found: Dict[int, SavedContact], candidate: SavedContact
) -> None:
    """Keep the richest entry per chat id; address-book entries win."""
    prev = found.get(candidate.chat_id)
    if prev is None:
        found[candidate.chat_id] = candidate
        return
    if prev.source == "contacts" and candidate.source != "contacts":
        return
    if candidate.source == "contacts" and prev.source != "contacts":
        found[candidate.chat_id] = candidate
        return
    if not prev.local_name and candidate.local_name:
        found[candidate.chat_id] = candidate


async def _merge_users(
    client: Any,
    peers: Sequence[Any],
    found: Dict[int, SavedContact],
    *,
    source: str,
    chunk_size: int,
    chat_type: Any = None,
) -> None:
    """Resolve peers → users (batched) and merge them into ``found``."""
    peers = [p for p in peers if peer_chat_id(p) > 0]
    if not peers:
        return
    step = max(1, int(chunk_size))
    for start in range(0, len(peers), step):
        batch = peers[start : start + step]
        users: List[Any] = []
        try:
            loaded = await client.load_users(batch)
            users = list(loaded or [])
        except Exception:
            users = []
        if not users:
            users = await _load_users_individually(client, batch, chat_type=chat_type)
        for user in users:
            contact = contact_from_user(user, source=source)
            if contact is not None:
                _merge_contact(found, contact)


async def _load_users_individually(
    client: Any, peers: Sequence[Any], *, chat_type: Any = None
) -> List[Any]:
    """Fallback when the batch ``load_users`` call fails for a chunk."""
    out: List[Any] = []
    for peer in peers:
        try:
            user = await client.load_user(
                chat_id=peer_chat_id(peer), chat_type=chat_type
            )
        except Exception:
            continue
        if user is not None:
            out.append(user)
    return out


async def build_contact_index(
    client: Any,
    *,
    include_dialogs: bool = True,
    dialog_limit: int = 200,
    chunk_size: int = 50,
) -> ContactIndex:
    """Index the account's saved contacts (and optionally dialog partners).

    Args:
        include_dialogs: also index 1-on-1 peers from recent dialogs, so people
            who wrote to us but were never saved as a contact are reachable by
            their profile name.
        dialog_limit: how many recent dialogs to scan (rate-limit guard).
        chunk_size: peers per ``load_users`` call.
    """
    found: Dict[int, SavedContact] = {}
    chat_type = _private_chat_type()
    notes: List[str] = []

    peers: List[Any] = []
    try:
        peers = list(await client.load_contacts() or [])
        notes.append(f"address book: {len(peers)}")
    except Exception as exc:
        peers = []
        notes.append(f"address book failed: {type(exc).__name__}")
    await _merge_users(
        client, peers, found, source="contacts", chunk_size=chunk_size,
        chat_type=chat_type,
    )

    if include_dialogs:
        dialog_peers: Dict[int, Any] = {}
        try:
            dialogs = list(await client.load_dialogs(limit=dialog_limit) or [])
            notes.append(f"dialogs: {len(dialogs)}")
        except Exception as exc:
            dialogs = []
            notes.append(f"dialogs failed: {type(exc).__name__}")
        for dialog in dialogs:
            peer = getattr(dialog, "peer", None)
            if peer is None or not peer_is_private(peer):
                continue
            dialog_peers.setdefault(peer_chat_id(peer), peer)
        await _merge_users(
            client,
            list(dialog_peers.values()),
            found,
            source="dialog",
            chunk_size=chunk_size,
            chat_type=chat_type,
        )

    index = ContactIndex(found.values())
    index.notes = notes
    return index
