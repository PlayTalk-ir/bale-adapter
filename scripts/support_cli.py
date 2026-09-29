#!/usr/bin/env python3
"""
scripts/support_cli.py — support-agent tools for the shared PlayTalk Bale account.

Subcommands (for AI agents or humans):
    send          Send a message to phones, chat ids or saved contact names
    contacts      List/search saved contacts with their chat ids
    inbox         List dialogs; show account-wide or per-agent unread
    sync          Pull recent history into the local inbox store
    collect       Export customer messages for FAQ topic generation
    analyze       Summarize current customer concerns by category
    ack           Mark a chat handled for a specific support agent

Examples:
    python scripts/support_cli.py inbox --unread
    python scripts/support_cli.py inbox --agent sara
    python scripts/support_cli.py sync --dialogs 50 --history 30
    python scripts/support_cli.py contacts --refresh
    python scripts/support_cli.py contacts --search نفس
    python scripts/support_cli.py contacts --add "آرن داودی=164862466"
    python scripts/support_cli.py send --to "نفس پیروز" --text "سلام" --dry-run
    python scripts/support_cli.py send --to 09924466793,123456 --text "سلام"
    python scripts/support_cli.py send --to-file recipients.xlsx --column B --dry-run
    python scripts/support_cli.py send --to-file names.txt --text "متن پیام"
    python scripts/support_cli.py collect --limit 100 --json
    python scripts/support_cli.py analyze
    python scripts/support_cli.py ack --agent sara --chat 123456 --message-id 999
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform.analysis import analyze_concerns, collect_for_faq
from bale_platform.config import BaleUserbotConfig
from bale_platform.contact_store import DEFAULT_CONTACTS_PATH, ContactBook, refresh_book
from bale_platform.contacts import ContactIndex
from bale_platform.inbox import (
    account_unread_dialogs,
    agent_unread,
    list_dialogs,
    sync_dialog_history,
)
from bale_platform.outbound import (
    TARGET_CHAT_ID,
    TARGET_NAME,
    TARGET_PHONE,
    classify_target,
    resolve_target,
    send_to_targets,
)
from bale_platform.phone import to_ascii_digits
from bale_platform.session import bale_client
from bale_platform.store import SupportStore, DEFAULT_STORE_PATH
from bale_platform.targets import load_targets


def _store_path(cfg: BaleUserbotConfig) -> Path:
    return Path(os.getenv("BALE_STORE_PATH", str(DEFAULT_STORE_PATH)))


def _contacts_path() -> Path:
    return Path(os.getenv("BALE_CONTACTS_PATH", str(DEFAULT_CONTACTS_PATH)))


def _header_flag(args: argparse.Namespace) -> bool | None:
    """True = skip first row, False = keep it, None = auto-detect."""
    if getattr(args, "has_header", False):
        return True
    if getattr(args, "no_header", False):
        return False
    return None


async def cmd_send(args: argparse.Namespace) -> int:
    try:
        targets = load_targets(
            args.to,
            args.to_file,
            column=args.column,
            sheet=args.sheet,
            has_header=_header_flag(args),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2

    if not targets:
        print("[err] no targets — pass --to and/or --to-file", file=sys.stderr)
        return 2

    by_name = [t for t in targets if classify_target(t) == TARGET_NAME]
    print(f"# targets: {len(targets)} ({len(by_name)} by saved name)")

    async with bale_client() as client:
        store = SupportStore(_store_path(BaleUserbotConfig.from_env()))
        index: ContactIndex | None = None
        if by_name and not args.no_names:
            book = ContactBook(_contacts_path())
            if len(book):
                index = book.to_index()
                print(f"# contact book: {len(index)} entries ({book.path})")
            else:
                print(
                    "[err] contact book is empty — names cannot be resolved",
                    file=sys.stderr,
                )
                print(
                    "      seed it:  python scripts/support_cli.py contacts --refresh",
                    file=sys.stderr,
                )
                print(
                    '      add one:  python scripts/support_cli.py contacts --add "NAME=CHAT_ID"',
                    file=sys.stderr,
                )
                if len(by_name) == len(targets):
                    return 2
                print("[warn] continuing with phone/chat-id targets only", file=sys.stderr)

        def _progress(position: int, total: int, target: str) -> None:
            print(f"... [{position}/{total}] {target}")

        results = await send_to_targets(
            client,
            targets,
            args.text,
            store=store,
            dry_run=args.dry_run,
            index=index,
            delay=args.delay,
            on_progress=_progress if args.progress else None,
        )

    ok = 0
    for r in results:
        status = "OK" if r.ok else "FAIL"
        matched = f" → {r.matched_name}" if r.matched_name else ""
        print(f"[{status}] target={r.target}{matched} chat_id={r.chat_id} — {r.detail}")
        ok += 1 if r.ok else 0
    if any("no saved contact matches" in r.detail for r in results):
        print(
            '# hint: unknown name — seed the book (contacts --refresh) '
            'or add it: contacts --add "NAME=CHAT_ID"'
        )
    suffix = " (dry-run — nothing sent)" if args.dry_run else ""
    print(f"# {ok}/{len(results)} ok{suffix}")
    return 0 if results and ok == len(results) else 1


async def cmd_contacts(args: argparse.Namespace) -> int:
    book = ContactBook(_contacts_path())

    if args.refresh or args.add or args.remove:
        code = await _apply_book_changes(args, book)
        if code:
            return code

    rows = book.search(args.search, limit=args.limit) if args.search else book.all()
    if not args.search and args.limit > 0:
        rows = rows[: args.limit]

    if args.json:
        print(json.dumps([e.as_dict() for e in rows], ensure_ascii=False, indent=2))
        return 0

    for entry in rows:
        parts = [f"chat={entry.chat_id}", f"name={entry.name!r}"]
        if entry.local_name and entry.local_name != entry.name:
            parts.append(f"local={entry.local_name!r}")
        if entry.profile_name and entry.profile_name != entry.name:
            parts.append(f"profile={entry.profile_name!r}")
        if entry.username:
            parts.append(f"username=@{entry.username}")
        parts.append("[manual]" if entry.manual else f"[{entry.source}]")
        print(" ".join(parts))
    if not rows:
        print("# no contact matched")

    stats = book.stats()
    origin = ", ".join(f"{key}={value}" for key, value in sorted(stats.items()))
    print(f"# showing {len(rows)} of {len(book)} book entries ({origin or 'empty'})")
    print(f"# book file: {book.path}")
    if not len(book):
        print("# hint: python scripts/support_cli.py contacts --refresh")
    return 0


def _split_add_spec(spec: str) -> tuple[str, str]:
    """``'NAME=ID'`` / ``'ID'`` → ``(name, target)``."""
    text = str(spec or "").strip()
    if "=" in text:
        name, _, target = text.partition("=")
        return name.strip(), target.strip()
    return text, ""


async def _add_one(
    book: ContactBook, client: Any, name: str, target: str
) -> None:
    if not target:
        print(
            f"[err] --add {name!r} needs a chat id or phone: --add \"NAME=CHAT_ID\"",
            file=sys.stderr,
        )
        return

    kind = classify_target(target)
    if kind == TARGET_PHONE:
        if client is None:
            print(f"[err] {target} is a phone — a session is required", file=sys.stderr)
            return
        resolved = await resolve_target(client, target)
        if not resolved.chat_id:
            print(f"[FAIL] {name or target}: {resolved.error}", file=sys.stderr)
            return
        chat_id = resolved.chat_id
        print(f"# phone {target} resolved to chat_id={chat_id}")
    elif kind == TARGET_CHAT_ID:
        digits = to_ascii_digits(target).replace(" ", "").replace("-", "")
        chat_id = int(digits)
    else:
        print(
            f"[err] --add {name}={target}: right side must be a chat id or a phone",
            file=sys.stderr,
        )
        return

    entry = book.add_manual(name or str(chat_id), chat_id)
    print(f"# manual entry: chat={entry.chat_id} name={entry.name!r} [manual]")


async def _apply_book_changes(args: argparse.Namespace, book: ContactBook) -> int:
    for raw in args.remove or []:
        text = str(raw).strip()
        if not text.isdigit():
            print(f"[err] --remove expects a chat id, got {text!r}", file=sys.stderr)
            return 2
        if book.remove(text):
            print(f"# removed chat_id={text}")
        else:
            print(f"[warn] chat_id={text} was not in the book", file=sys.stderr)

    adds = [_split_add_spec(spec) for spec in (args.add or [])]
    needs_client = args.refresh or any(
        classify_target(target) == TARGET_PHONE for _, target in adds
    )

    if needs_client:
        async with bale_client() as client:
            if args.refresh:
                counts = await refresh_book(
                    book,
                    client,
                    dialog_limit=0 if args.no_dialogs else args.dialog_limit,
                    prune=args.prune,
                )
                notes = "; ".join(counts.pop("notes", []) or [])
                summary = ", ".join(f"{key}={value}" for key, value in counts.items())
                print(f"# refresh: {summary}" + (f" [{notes}]" if notes else ""))
            for name, target in adds:
                await _add_one(book, client, name, target)
    else:
        for name, target in adds:
            await _add_one(book, None, name, target)
    return 0



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

    send_p = sub.add_parser(
        "send", help="send a message to phones, chat ids or saved contact names"
    )
    send_p.add_argument(
        "--to",
        help="targets split by comma/semicolon/newline — phone, chat id or saved name",
    )
    send_p.add_argument(
        "--to-file",
        help="targets from .xlsx/.xlsm (Excel), .csv/.tsv or a text file (one per line)",
    )
    send_p.add_argument(
        "--column", help="Excel/CSV column: letter (A, B) or 1-based number"
    )
    send_p.add_argument(
        "--sheet", help="Excel sheet name or 1-based number (default: first sheet)"
    )
    header_group = send_p.add_mutually_exclusive_group()
    header_group.add_argument(
        "--has-header", action="store_true", help="first row is a title — skip it"
    )
    header_group.add_argument(
        "--no-header", action="store_true", help="never skip a row"
    )
    send_p.add_argument("--text", required=True, help="message body")
    send_p.add_argument("--dry-run", action="store_true", help="resolve targets, send nothing")
    send_p.add_argument(
        "--delay", type=float, default=1.0, help="seconds between real sends (default 1.0)"
    )
    send_p.add_argument(
        "--progress", action="store_true", help="print progress for every target"
    )
    send_p.add_argument(
        "--no-names", action="store_true", help="skip the contact book (phones/ids only)"
    )

    contacts_p = sub.add_parser(
        "contacts",
        help="local contact book: list / refresh from Bale / add manually",
        description=(
            "Local contact book (data/contacts.sqlite). `--refresh` pours in everyone "
            "we have chatted with; people that are still missing are added by hand and "
            "survive every refresh."
        ),
    )
    contacts_p.add_argument("--search", help="fuzzy name filter (Persian-friendly)")
    contacts_p.add_argument("--limit", type=int, default=50, help="rows to print (0 = all)")
    contacts_p.add_argument("--json", action="store_true")
    contacts_p.add_argument(
        "--refresh", action="store_true", help="pull dialogs + address book into the book"
    )
    contacts_p.add_argument(
        "--no-dialogs", action="store_true", help="with --refresh: address book only"
    )
    contacts_p.add_argument(
        "--dialog-limit", type=int, default=200, help="with --refresh: dialogs to scan"
    )
    contacts_p.add_argument(
        "--prune",
        action="store_true",
        help="with --refresh: drop non-manual rows Bale no longer reports",
    )
    contacts_p.add_argument(
        "--add",
        action="append",
        metavar="NAME=TARGET",
        help='manual entry, repeatable — "آرن داودی=164862466" or "آرن=09924466793"',
    )
    contacts_p.add_argument(
        "--remove", action="append", metavar="CHAT_ID", help="delete an entry (repeatable)"
    )

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
    if args.cmd == "contacts":
        return await cmd_contacts(args)
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
