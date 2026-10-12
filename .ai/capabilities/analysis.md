# Capability: analysis & FAQ

## Sync then analyze

```bash
python scripts/support_cli.py sync
python scripts/support_cli.py analyze --json
```

## Collect for FAQ topics

```bash
python scripts/support_cli.py collect --json --limit 50
```

## Sample agent tasks

- Summarize top customer concerns this week
- Propose FAQ titles from `collect` output
- Compare `sales` vs `technical` volume

See category rules in `.ai/design/analysis.md`.

## FAQ layer (no LLM, suggestions only)

```bash
python scripts/support_cli.py faq --text "آدرس سرور چیه؟"
python scripts/support_cli.py faq --backtest --days 7 --exclude-chat 10 --show none
```

Entries live in `bale_platform/faq_entries.yaml` (facts must be confirmed by a
manager). The matcher never sends: `suggest` drafts need human approval,
`escalate` (disputes / churn) is never answered, `no_reply` is thanks/ack.
