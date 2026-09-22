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

## Rules

- Confirm text with human before sending without `--dry-run`
- Resolve failures per target in CLI output (`OK` / `FAIL`)
