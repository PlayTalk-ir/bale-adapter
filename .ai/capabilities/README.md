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

Optional. `python -m bale_platform.mcp_server` calls the HTTP API with a bearer token ([docs/mcp.md](../../docs/mcp.md)). It can list the shared inbox feed, read a chat, search contacts, and queue one outbox send. Per-agent unread, ack, KB facts, and FAQ mining stay on this CLI until the API grows routes for them.

## Hard limits

- No OTP / login on behalf of human
- No auto-send without human approval (use `--dry-run` first)
- No edits to `.ai/architecture/`
