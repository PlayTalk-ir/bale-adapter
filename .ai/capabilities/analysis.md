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
