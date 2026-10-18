# Capabilities

What support AI agents can do via terminal (after activate + session exists).

| Capability | Doc |
|------------|-----|
| Read inbox / unread | [inbox.md](inbox.md) |
| Send messages | [outbound.md](outbound.md) |
| Saved contacts by name | [outbound.md](outbound.md) |
| Contact book (local) | [outbound.md](outbound.md) |
| FAQ mining | [analysis.md](analysis.md) |
| Live listen | [runner.md](runner.md) |
| Admin panel (for humans — no CLI) | [../setup/panel.md](../setup/panel.md) |

## MCP

Optional. `python -m bale_platform.mcp_server` calls the HTTP API with a bearer token ([docs/mcp.md](../../docs/mcp.md)). It can list per-agent unread, ack a chat, read KB facts, summarize stored FAQ topics, and queue one outbox send. FAQ and unread read the adapter's stored data; they do not sync from Bale.

## Hard limits

- No OTP / login on behalf of human
- No auto-send without human approval (use `--dry-run` first)
- No edits to `.ai/architecture/`
