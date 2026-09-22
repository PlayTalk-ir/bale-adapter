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

## 4. After replying

```bash
python scripts/support_cli.py ack --agent YOUR_NAME --chat ID --message-id ID
```

Use one consistent `YOUR_NAME` per support person.
