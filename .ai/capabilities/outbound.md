# Capability: outbound send

## Dry run (always first)

```bash
python scripts/support_cli.py send --to 09924466793 --text "سلام" --dry-run
```

## Send to list

```bash
python scripts/support_cli.py send --to 09xx,09yy,CHAT_ID --text "متن پیام"
```

Targets: local `09…` phones, `98…`, or numeric Bale chat id.

## HTTP API (Steach backend)

When enabled on the VPS (`BALE_API_ENABLED=true`), Laravel calls the adapter over Bearer auth. See [docs/api.md](../../docs/api.md).

## Rules

- Confirm text with human before sending without `--dry-run`
- Resolve failures per target in CLI output (`OK` / `FAIL`)
