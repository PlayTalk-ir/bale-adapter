# Message flow

```
Bale WebSocket (aiobale)
        │
        ▼
BaleUserbotAdapter._on_message
        │
        ├──► SupportStore.upsert_message (inbox cache)
        │
        └──► kb.learn.extract_fact → learned_facts.mdl (structured only)
```

## Runner vs CLI

| Mode | When |
|------|------|
| `bale_platform.runner` | Continuous listen |
| `support_cli.py sync` | One-shot backfill |

Both write to the same SQLite store.

## Outbound

`support_cli.py send` → `outbound.send_to_targets` → aiobale `send_message`
→ also upserts `direction=out` in store.
