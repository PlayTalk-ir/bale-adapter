# CLI surface

Entry: `python scripts/support_cli.py <cmd>`

Always activate venv first (`activate.ps1` / `activate.sh`).

| Cmd | Purpose |
|-----|---------|
| `sync` | Pull dialog history into SQLite |
| `inbox` | List dialogs; `--unread` or `--agent NAME` |
| `collect` | Export messages for FAQ (`--json`) |
| `analyze` | Summarize concerns by category |
| `send` | Message to phones/chat ids; use `--dry-run` first |
| `ack` | Mark chat handled for an agent |

## Common flags

- `--dialogs N` / `--history N` — sync depth
- `--limit N` — collect/analyze cap
- `--sync-first` — sync before read commands

## Phone normalization

`09XXXXXXXXX` → `989XXXXXXXXX` via `bale_platform/phone.py`
