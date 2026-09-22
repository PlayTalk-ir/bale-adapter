"""Lightweight concern analysis for support agents (no LLM required)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from bale_platform.store import StoredMessage


@dataclass
class ConcernBucket:
    category: str
    count: int
    examples: List[str]


CATEGORY_RULES = [
    ("sales", r"(?i)(price|cost|fee|buy|register|enroll|signup|قیمت|ثبت.?نام|خرید)"),
    ("education", r"(?i)(level|lesson|teacher|class|homework|سطح|درس|مدرس|جلسه)"),
    ("technical", r"(?i)(login|password|minecraft|server|lag|install|error|ورود|لاگین|سرور|ماین)"),
    ("gaming", r"(?i)(world|spawn|plugin|npc|game|world|بازی|ورلد)"),
]


def classify_text(text: str) -> str:
    for category, pattern in CATEGORY_RULES:
        if re.search(pattern, text):
            return category
    return "general"


def analyze_concerns(
    messages: List[StoredMessage],
    *,
    incoming_only: bool = True,
    top_n: int = 5,
) -> Dict[str, object]:
    """Summarize what customers are asking about right now."""
    rows = [m for m in messages if (not incoming_only or m.direction == "in")]
    by_category: Dict[str, List[str]] = defaultdict(list)
    for m in rows:
        by_category[classify_text(m.text)].append(m.text.strip())

    buckets: List[ConcernBucket] = []
    for category, texts in sorted(
        by_category.items(), key=lambda kv: len(kv[1]), reverse=True
    ):
        buckets.append(
            ConcernBucket(
                category=category,
                count=len(texts),
                examples=texts[:top_n],
            )
        )

    # Simple phrase frequency for FAQ topic hints (Persian + Latin words >= 4 chars)
    tokens: Counter[str] = Counter()
    for m in rows:
        for tok in re.findall(r"[\w\u0600-\u06FF]{4,}", m.text.lower()):
            if tok.isdigit():
                continue
            tokens[tok] += 1

    faq_hints = [w for w, _ in tokens.most_common(15)]

    return {
        "total_messages": len(rows),
        "categories": [
            {"category": b.category, "count": b.count, "examples": b.examples}
            for b in buckets
        ],
        "faq_topic_hints": faq_hints,
    }


def collect_for_faq(
    messages: List[StoredMessage],
    *,
    incoming_only: bool = True,
    limit: int = 100,
) -> List[Dict[str, str]]:
    rows = [m for m in messages if (not incoming_only or m.direction == "in")]
    rows.sort(key=lambda m: m.date_ms, reverse=True)
    out: List[Dict[str, str]] = []
    for m in rows[:limit]:
        out.append(
            {
                "chat_id": m.chat_id,
                "timestamp": m.timestamp,
                "text": m.text,
                "category": classify_text(m.text),
            }
        )
    return out
