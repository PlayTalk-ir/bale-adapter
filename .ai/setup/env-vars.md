# Environment variables

Set automatically by `activate.ps1` / `activate.sh` for local dev.

| Variable | Local default | Purpose |
|----------|---------------|---------|
| `BALE_SESSION_PATH` | `.session/session.bale` | aiobale session |
| `BALE_KB_DIR` | `kb/` | KB output |
| `BALE_LOG_FILE` | `logs/userbot.log` | Logs |
| `BALE_STORE_PATH` | `data/support_inbox.sqlite` | Inbox DB |
| `BALE_OBSERVE_ONLY` | `true` | No auto-reply |
| `BALE_API_ENABLED` | `false` | HTTP API + outbox worker |
| `BALE_ADAPTER_API_TOKENS` | _(empty)_ | Comma-separated API bearer tokens |
| `BALE_OUTBOX_PATH` | `data/outbox.sqlite` | Outbound queue DB |
| `BALE_PHONE_PEPPER` | _(empty)_ | Phone cache HMAC (set in `.env.secrets` on VPS) |
| `PYTHONIOENCODING` | `utf-8` (Windows) | Emoji in login |
| `PYTHONPATH` | repo root | Imports |

Full API/outbox knobs: [docs/api.md](../../docs/api.md).

Production values: `.ai/architecture/deploy.md`
