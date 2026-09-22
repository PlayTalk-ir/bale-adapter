# Environment variables

Set automatically by `activate.ps1` / `activate.sh` for local dev.

| Variable | Local default | Purpose |
|----------|---------------|---------|
| `BALE_SESSION_PATH` | `.session/session.bale` | aiobale session |
| `BALE_KB_DIR` | `kb/` | KB output |
| `BALE_LOG_FILE` | `logs/userbot.log` | Logs |
| `BALE_STORE_PATH` | `data/support_inbox.sqlite` | Inbox DB |
| `BALE_OBSERVE_ONLY` | `true` | No auto-reply |
| `PYTHONIOENCODING` | `utf-8` (Windows) | Emoji in login |
| `PYTHONPATH` | repo root | Imports |

Production values: `.ai/architecture/deploy.md`
