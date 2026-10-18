# Inbox store design

Path: `data/support_inbox.sqlite` (override: `BALE_STORE_PATH`)

## Tables

**messages** — chat_id, message_id, sender_id, text, timestamp, direction (`in`|`out`), seq (monotonic cursor, stable across updates), kind (default `text`)

**agent_acks** — agent_id, chat_id, last_message_id, acked_at

**chat_labels** — display names per chat (runner on inbound, backfill on `sync`)

## Per-agent unread

```
unread for agent A = incoming messages where message_id > A's last ack on that chat
```

Excludes messages sent by the company account (`sender_id == me`).

## Population

1. **Runner** — real-time via `BaleUserbotAdapter._on_message`
2. **sync** — backfill from `load_dialogs` + `load_history`

## ack workflow

After human finishes a chat:

```bash
python scripts/support_cli.py ack --agent NAME --chat ID --message-id ID
```

HTTP: `POST /v1/inbox/ack` uses `ack_at_least` (same or older id is a no-op). `GET /v1/inbox/unread?agent=` lists incoming private messages above that cursor. The CLI `ack` command can still replace the cursor outright.
