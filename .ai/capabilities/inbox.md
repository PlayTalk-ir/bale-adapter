# Capability: inbox

## Account-wide unread

```bash
python scripts/support_cli.py inbox --unread
```

Uses Bale native `unread_count` on shared login.

## Per-agent unread

```bash
python scripts/support_cli.py inbox --agent YOUR_NAME --sync-first
```

Requires ack history in SQLite. See `.ai/design/inbox-store.md`.

## List all dialogs

```bash
python scripts/support_cli.py inbox
python scripts/support_cli.py inbox --all-chats
```

## Mark handled

```bash
python scripts/support_cli.py ack --agent YOUR_NAME --chat CHAT_ID --message-id MSG_ID
```
