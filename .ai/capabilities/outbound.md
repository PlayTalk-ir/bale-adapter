# Capability: outbound send

## Dry run (always first)

```bash
python scripts/support_cli.py send --to 09924466793 --text "سلام" --dry-run
python scripts/support_cli.py send --to "نفس پیروز" --text "سلام" --dry-run
```

## Send to list

```bash
python scripts/support_cli.py send --to 09xx,09yy,CHAT_ID --text "متن پیام"
python scripts/support_cli.py send --to "نفس پیروز,امیرحافظ" --text "متن پیام"
```

Targets: local `09…` phones, `98…`, numeric Bale chat id, or a **saved contact
name** — names resolve against the local contact book (`data/contacts.sqlite`),
not against a live Bale lookup.

## Contact book (seed once, then reuse)

```bash
python scripts/support_cli.py contacts --refresh              # everyone we chatted with
python scripts/support_cli.py contacts --search نفس
python scripts/support_cli.py contacts --add "آرن داودی=164862466"
python scripts/support_cli.py contacts --add "نفر جدید=09924466793"
python scripts/support_cli.py contacts --remove 123456
```

- `--refresh` keeps every manual entry: a name you typed is never overwritten,
  and `--prune` only drops non-manual rows.
- Names that are not in the book yet fail with a clear hint instead of guessing.

## Bulk lists — Excel or one target per line

```bash
python scripts/support_cli.py send --to-file recipients.xlsx --column B --text "متن پیام" --dry-run
python scripts/support_cli.py send --to-file names.txt --text "متن پیام"
python scripts/support_cli.py send --to-file names.csv --column 1 --sheet "مخاطبین" --text "متن پیام"
```

- Excel `.xlsx`/`.xlsm`, CSV/TSV (`,` `;` or tab), or any text file where each
  name/number is on its own line.
- `--column` takes a letter (`A`) or 1-based number; a title row is skipped
  automatically (`--has-header` / `--no-header` to force).
- Names that match several contacts are reported as `FAIL` with the candidate
  chat ids — fix the list instead of guessing.

## Before a real send

1. `python scripts/support_cli.py contacts --refresh` — seed/update the book.
2. `python scripts/support_cli.py contacts --search NAME` — confirm the chat id.
3. `send … --dry-run` — confirm every target resolves.
4. Then send without `--dry-run` (text confirmed by a human first).

## HTTP API (Steach backend)

When enabled on the VPS (`BALE_API_ENABLED=true`), Laravel calls the adapter over Bearer auth. See [docs/api.md](../../docs/api.md).

## Rules

- Confirm text with human before sending without `--dry-run`
- Resolve failures per target in CLI output (`OK` / `FAIL`)
- Keep `--delay` (default 1.0s) for bulk sends — aiobale is unofficial

