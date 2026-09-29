# Daily workflow

## 1. Listen (optional background terminal)

```bash
python -m bale_platform.runner
```

## 2. Or sync on demand

```bash
python scripts/support_cli.py sync --dialogs 50 --history 30
```

## 3. Work inbox

```bash
python scripts/support_cli.py inbox --agent YOUR_NAME
python scripts/support_cli.py analyze
```

## 3b. Contact book (seed once, then reuse)

```bash
python scripts/support_cli.py contacts --refresh            # everyone we chatted with
python scripts/support_cli.py contacts --search نفس
python scripts/support_cli.py contacts --add "نفر جدید=09924466793"
python scripts/support_cli.py contacts --add "آرن داودی=164862466"
```

Manual entries survive `--refresh`; re-run `--refresh` weekly to pick up new chats.

## 3c. Bulk message (Excel or one name per line)

```bash
python scripts/support_cli.py send --to-file recipients.xlsx --column B --text "متن پیام" --dry-run
python scripts/support_cli.py send --to-file names.txt --text "متن پیام"
```

Confirm the dry-run output (`OK` per target) before dropping `--dry-run`.

## 4. After replying

```bash
python scripts/support_cli.py ack --agent YOUR_NAME --chat ID --message-id ID
```

Use one consistent `YOUR_NAME` per support person.
