# CLI surface

Entry: `python scripts/support_cli.py <cmd>`

Always activate venv first (`activate.ps1` / `activate.sh`).

| Cmd | Purpose |
|-----|---------|
| `sync` | Pull dialog history into SQLite |
| `inbox` | List dialogs; `--unread` or `--agent NAME` |
| `contacts` | Local contact book: list / refresh / add |
| `collect` | Export messages for FAQ (`--json`) |
| `analyze` | Summarize concerns by category |
| `send` | Message phones / chat ids / saved names; `--dry-run` first |
| `ack` | Mark chat handled for an agent |

## Common flags

- `--dialogs N` / `--history N` — sync depth
- `--limit N` — collect/analyze cap (0 = all for `contacts`)
- `--sync-first` — sync before read commands

## send targets

| Input | Kind | Example |
|-------|------|---------|
| saved contact name | name | `--to "نفس پیروز"` |
| phone | phone | `--to 09924466793` |
| chat id | id | `--to 1858791866` |

- `--to` splits on comma, semicolon, `،`, tab and newlines.
- `--to-file` accepts `.xlsx`/`.xlsm` (Excel), `.csv`/`.tsv`, or a text file
  with one target per line (`-` bullets and `1.` numbering are stripped).
- `--column A` (letter or 1-based number) picks the Excel/CSV column; titles are
  auto-skipped (`--has-header` / `--no-header` to force).
- `--sheet NAME|N` picks the worksheet (default: first).
- Names resolve against the **local contact book** (`data/contacts.sqlite`), so a
  name send costs no extra API calls. Seed it with `contacts --refresh`, add
  missing people with `contacts --add "NAME=CHAT_ID"`.
- `--no-names` skips the book entirely (phones / chat ids only).
- `--delay SECONDS` (default 1.0) spaces out real sends; `--progress` prints each target.

Resolution rules, the book and ambiguity handling: [contacts.md](contacts.md).

## Phone normalization

`09XXXXXXXXX` → `989XXXXXXXXX` via `bale_platform/phone.py`; Persian digits
(`۰۹…`) are converted first.

