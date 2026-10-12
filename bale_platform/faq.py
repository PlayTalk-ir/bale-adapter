"""FAQ matcher for customer chats — no LLM, no network, suggestions only.

Maps an incoming Persian message to a canned answer from ``faq_entries.yaml``.
Nothing here sends anything: callers get a ``FaqMatch`` and a human decides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import yaml

from bale_platform.store import StoredMessage

ENTRIES_PATH = Path(__file__).with_name("faq_entries.yaml")

_FOLD = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ؤ": "و",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "‌": " ",
        **{c: str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")},
        **{c: str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")},
    }
)
_MARKS = re.compile(r"[ً-ٰٟـ​‍-‏]")
_NON_WORD = re.compile(
    r"[^\w؀-ۿ]+|[،؛؟٪-٭۔]+"
)


def fold(text: str) -> str:
    """Unify Arabic/Persian letter variants and digits; keep punctuation."""
    return _MARKS.sub("", text.translate(_FOLD)).lower()


def normalize(text: str) -> str:
    """Folded text with punctuation/emoji removed and spaces collapsed."""
    return _NON_WORD.sub(" ", fold(text)).strip()


@dataclass(frozen=True)
class FaqEntry:
    id: str
    kind: str  # "answer" | "escalate" | "no_reply"
    category: str
    risk: str  # "safe" | "review"
    answer: str
    reason: str
    patterns: tuple[re.Pattern[str], ...]
    full_patterns: tuple[re.Pattern[str], ...]


@dataclass
class FaqMatch:
    action: str  # "suggest" | "escalate" | "no_reply" | "none"
    entry_id: Optional[str] = None
    category: Optional[str] = None
    risk: Optional[str] = None
    answer: str = ""
    confidence: float = 0.0
    reason: str = ""
    alternates: List[str] = field(default_factory=list)


def _compile(patterns: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(fold(p)) for p in patterns or [])


@lru_cache(maxsize=4)
def load_entries(path: Path = ENTRIES_PATH) -> tuple[FaqEntry, ...]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries: List[FaqEntry] = []
    for item in raw["entries"]:
        entries.append(
            FaqEntry(
                id=item["id"],
                kind=item.get("kind", "answer"),
                category=item.get("category", "general"),
                risk=item.get("risk", "review"),
                answer=item.get("answer", ""),
                reason=item.get("reason", ""),
                patterns=_compile(item.get("patterns")),
                full_patterns=_compile(item.get("full_patterns")),
            )
        )
    return tuple(entries)


def match_faq(text: str, entries: Optional[Sequence[FaqEntry]] = None) -> FaqMatch:
    """Best FAQ suggestion for one customer message (or burst of messages)."""
    entries = entries if entries is not None else load_entries()
    norm = normalize(text)

    if not norm:  # emoji / punctuation only
        return FaqMatch(action="no_reply", reason="empty after normalization")

    for e in entries:
        if e.kind == "no_reply" and any(p.fullmatch(norm) for p in e.full_patterns):
            return FaqMatch(
                action="no_reply", entry_id=e.id, category=e.category, risk=e.risk
            )

    hits: Dict[str, int] = {}
    for e in entries:
        if e.kind == "no_reply":
            continue
        n = sum(1 for p in e.patterns if p.search(norm))
        if n:
            hits[e.id] = n
    if not hits:
        return FaqMatch(action="none", reason="no pattern matched")

    by_id = {e.id: e for e in entries}

    # A dispute / churn signal always wins: never auto-answer around it.
    esc = [i for i in hits if by_id[i].kind == "escalate"]
    if esc:
        e = by_id[esc[0]]
        return FaqMatch(
            action="escalate",
            entry_id=e.id,
            category=e.category,
            risk=e.risk,
            reason=e.reason,
            confidence=0.9,
            alternates=[i for i in hits if i != e.id],
        )

    order = {e.id: i for i, e in enumerate(entries)}
    ranked = sorted(hits, key=lambda i: (-hits[i], order[i]))
    best = by_id[ranked[0]]
    tied = [i for i in ranked if hits[i] == hits[best.id]]
    # Heuristic (not calibrated): a single clear topic in a short message is
    # trusted most; several topics or a long message needs a human eye.
    if len(tied) > 1:
        confidence = 0.5
    elif len(norm) > 160:
        confidence = 0.7
    else:
        confidence = 0.9
    return FaqMatch(
        action="suggest",
        entry_id=best.id,
        category=best.category,
        risk=best.risk,
        answer=best.answer,
        confidence=confidence,
        alternates=[i for i in ranked if i != best.id],
    )


def group_bursts(
    messages: Iterable[StoredMessage], *, gap_ms: int = 3 * 60 * 1000
) -> List[tuple[str, int, str]]:
    """Merge consecutive incoming messages of one chat into ``(chat, ts, text)``.

    Customers send a question as 3-6 short bubbles; matching bubble by bubble
    loses context. Outgoing messages break a burst.
    """
    out: List[tuple[str, int, str]] = []
    by_chat: Dict[str, List[StoredMessage]] = {}
    for m in messages:
        by_chat.setdefault(m.chat_id, []).append(m)
    for chat, msgs in by_chat.items():
        msgs.sort(key=lambda m: m.date_ms)
        cur: List[StoredMessage] = []
        for m in msgs:
            if m.direction != "in":
                if cur:
                    out.append((chat, cur[-1].date_ms, "\n".join(x.text for x in cur)))
                    cur = []
                continue
            if cur and m.date_ms - cur[-1].date_ms > gap_ms:
                out.append((chat, cur[-1].date_ms, "\n".join(x.text for x in cur)))
                cur = []
            cur.append(m)
        if cur:
            out.append((chat, cur[-1].date_ms, "\n".join(x.text for x in cur)))
    out.sort(key=lambda r: r[1])
    return out
