# Capability: live runner

Long-running listener (separate terminal):

```bash
python -m bale_platform.runner
```

- Writes to SQLite + `kb/learned_facts.mdl`
- Does **not** auto-reply (`BALE_OBSERVE_ONLY=true` default)
- Stop with Ctrl+C

If runner is down, use `support_cli.py sync` before inbox/analyze.
