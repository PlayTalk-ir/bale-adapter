# Design

AI-maintained implementation design. Update when code behavior changes.

## Files

| File | Topic |
|------|-------|
| [cli-surface.md](cli-surface.md) | `support_cli.py` commands |
| [inbox-store.md](inbox-store.md) | SQLite schema, per-agent unread |
| [message-flow.md](message-flow.md) | Runner → store → KB |
| [analysis.md](analysis.md) | Concern categories, FAQ mining |
| [privacy.md](privacy.md) | What is stored where |

## Update rules

- Keep files short; split rather than grow one doc.
- Reflect actual code in `bale_platform/` and `scripts/`.
- Do not duplicate `architecture/` — link instead.
