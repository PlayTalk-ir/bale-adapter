#!/usr/bin/env python3
"""
scripts/support_cli.py — support-agent tools for the shared PlayTalk Bale account.

Subcommands (for AI agents or humans):
    send          Send a message to one or more phones/chat ids
    inbox         List dialogs; show account-wide or per-agent unread
    sync          Pull recent history into the local inbox store
    collect       Export customer messages for FAQ topic generation
    analyze       Summarize current customer concerns by category
    ack           Mark a chat handled for a specific support agent

Examples:
    python scripts/support_cli.py inbox --unread
    python scripts/support_cli.py inbox --agent sara
    python scripts/support_cli.py sync --dialogs 50 --history 30
    python scripts/support_cli.py send --to 09924466793,123456 --text "سلام"
    python scripts/support_cli.py collect --limit 100 --json
    python scripts/support_cli.py analyze
    python scripts/support_cli.py ack --agent sara --chat 123456 --message-id 999
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform.analysis import analyze_concerns, collect_for_faq
from bale_platform.config import BaleUserbotConfig
from bale_platform.inbox import (
    account_unread_dialogs,
    agent_unread,
    list_dialogs,
    sync_dialog_history,
)
from bale_platform.outbound import send_to_targets
from bale_platform.session import bale_client
from bale_platform.store import SupportStore, DEFAULT_STORE_PATH


def _store_path(cfg: BaleUserbotConfig) -> Path:
    import os

    return Path(os.getenv("BALE_STORE_PATH", str(DEFAULT_STORE_PATH)))


async def cmd_send(args: argparse.Namespace) -> int:
    targets = [t.strip() for t in args.to.split(",") if t.strip()]
    async with bale_client() as client:
        store = SupportStore(_store_path(BaleUserbotConfig.from_env()))
        results = await send_to_targets(
            client, targets, args.text, store=store, dry_run=args.dry_run
        )
    for r in results:
        status = "OK" if r.ok else "FAIL"
        print(f"[{status}] target={r.target} chat_id={r.chat_id} — {r.detail}")
    return 0 if all(r.ok for r in results) else 1


async def cmd_inbox(args: argparse.Namespace) -> int:
    store = SupportStore(_store_path(BaleUserbotConfig.from_env()))
    async with bale_client() as client:
        dialogs = await list_dialogs(
            client, limit=args.dialogs, private_only=not args.all_chats
        )
        me = await client.get_me()
        my_id = str(getattr(me, "id", ""))

        if args.agent:
            if args.sync_first:
                n = await sync_dialog_history(
                    client, store, dialog_limit=args.dialogs, history_limit=args.history
                )
                print(f"# synced {n} messages into store\n")
            unread = agent_unread(store, args.agent, account_user_id=my_id)
            if not unread:
                print(f"No unread for agent={args.agent!r}")
                return 0
            for m in unread:
                print(
                    f"chat={m.chat_id} msg={m.message_id} at={m.timestamp}: {m.text[:160]}"
                )
            return 0

        if args.unread:
            dialogs = account_unread_dialogs(dialogs)
        for d in dialogs:
            mark = f" unread={d.unread_count}" if d.unread_count else ""
            print(
                f"chat={d.chat_id} type={d.chat_type} name={d.label!r}{mark} "
                f"last=[{d.last_timestamp}] {d.last_message[:120]}"
            )
    return 0


async def cmd_sync(args: argparse.Namespace) -> int:
    store = SupportStore(_store_path(BaleUserbotConfig.from_env()))
    async with bale_client() as client:
        n = await sync_dialog_history(
            client,
            store,
            dialog_limit=args.dialogs,
            history_limit=args.history,
            private_only=not args.all_chats,
        )
    print(f"synced {n} messages → {store.path}")
    return 0


async def cmd_collect(args: argparse.Namespace) -> int:
    store = SupportStore(_store_path(BaleUserbotConfig.from_env()))
    if args.sync_first:
        async with bale_client() as client:
            await sync_dialog_history(
                client, store, dialog_limit=args.dialogs, history_limit=args.history
            )
    rows = collect_for_faq(
        store.recent_messages(limit=args.limit, since_ms=args.since_ms),
        incoming_only=not args.all_messages,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            print(f"[{r['category']}] chat={r['chat_id']} {r['timestamp']}: {r['text'][:200]}")
    return 0


async def cmd_analyze(args: argparse.Namespace) -> int:
    store = SupportStore(_store_path(BaleUserbotConfig.from_env()))
    if args.sync_first:
        async with bale_client() as client:
            await sync_dialog_history(
                client, store, dialog_limit=args.dialogs, history_limit=args.history
            )
    summary = analyze_concerns(
        store.recent_messages(limit=args.limit, since_ms=args.since_ms),
        incoming_only=not args.all_messages,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Total incoming messages analyzed: {summary['total_messages']}\n")
        for bucket in summary["categories"]:
            print(f"## {bucket['category']} ({bucket['count']})")
            for ex in bucket["examples"][:3]:
                print(f"  - {ex[:160]}")
            print()
        print("FAQ topic hints:", ", ".join(summary["faq_topic_hints"][:10]))
    return 0


async def cmd_ack(args: argparse.Namespace) -> int:
    store = SupportStore(_store_path(BaleUserbotConfig.from_env()))
    store.ack_chat(args.agent, str(args.chat), args.message_id)
    print(f"acked chat={args.chat} up to message_id={args.message_id} for agent={args.agent!r}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="PlayTalk Bale support-agent CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    send_p = sub.add_parser("send", help="send a message to phones or chat ids")
    send_p.add_argument("--to", required=True, help="comma-separated phones or chat ids")
    send_p.add_argument("--text", required=True, help="message body")
    send_p.add_argument("--dry-run", action="store_true")

    inbox_p = sub.add_parser("inbox", help="list dialogs / unread")
    inbox_p.add_argument("--unread", action="store_true", help="account-wide unread dialogs")
    inbox_p.add_argument("--agent", help="show unread for this support agent")
    inbox_p.add_argument("--sync-first", action="store_true")
    inbox_p.add_argument("--dialogs", type=int, default=40)
    inbox_p.add_argument("--history", type=int, default=30)
    inbox_p.add_argument("--all-chats", action="store_true")

    sync_p = sub.add_parser("sync", help="pull recent history into local store")
    sync_p.add_argument("--dialogs", type=int, default=40)
    sync_p.add_argument("--history", type=int, default=30)
    sync_p.add_argument("--all-chats", action="store_true")

    collect_p = sub.add_parser("collect", help="export messages for FAQ mining")
    collect_p.add_argument("--limit", type=int, default=100)
    collect_p.add_argument("--since-ms", type=int, default=0)
    collect_p.add_argument("--json", action="store_true")
    collect_p.add_argument("--sync-first", action="store_true")
    collect_p.add_argument("--dialogs", type=int, default=40)
    collect_p.add_argument("--history", type=int, default=30)
    collect_p.add_argument("--all-messages", action="store_true")

    analyze_p = sub.add_parser("analyze", help="summarize customer concerns")
    analyze_p.add_argument("--limit", type=int, default=200)
    analyze_p.add_argument("--since-ms", type=int, default=0)
    analyze_p.add_argument("--json", action="store_true")
    analyze_p.add_argument("--sync-first", action="store_true")
    analyze_p.add_argument("--dialogs", type=int, default=40)
    analyze_p.add_argument("--history", type=int, default=30)
    analyze_p.add_argument("--all-messages", action="store_true")

    ack_p = sub.add_parser("ack", help="mark chat handled for an agent")
    ack_p.add_argument("--agent", required=True)
    ack_p.add_argument("--chat", required=True, type=int)
    ack_p.add_argument("--message-id", required=True, type=int)

    return p


async def _main(args: argparse.Namespace) -> int:
    if args.cmd == "send":
        return await cmd_send(args)
    if args.cmd == "inbox":
        return await cmd_inbox(args)
    if args.cmd == "sync":
        return await cmd_sync(args)
    if args.cmd == "collect":
        return await cmd_collect(args)
    if args.cmd == "analyze":
        return await cmd_analyze(args)
    if args.cmd == "ack":
        return await cmd_ack(args)
    return 2


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
