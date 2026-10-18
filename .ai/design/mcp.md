# MCP server

Thin client of the HTTP API. Code: `bale_platform/mcp_server/`. Entry: `python -m bale_platform.mcp_server`. Operator docs: [docs/mcp.md](../../docs/mcp.md).

- SDK: official `mcp` 2.x `MCPServer` (FastMCP's renamed class). Transports: stdio, streamable HTTP on `127.0.0.1:8790` (`/mcp`).
- Auth: `BALE_MCP_API_TOKEN` as `Authorization: Bearer`. No session file, no inbox/outbox SQLite.
- `send_message` → `POST /v1/messages` (one recipient). Annotations: destructive, not read-only, not idempotent. Same idempotency key replays; a new key queues again.
- Read tools return API JSON unchanged (masked phones stay masked).
- Contact search downloads `GET /v1/contacts` and filters locally (`normalize_name`).
- Not wrapped, because the API has no route: per-agent unread, ack, KB facts, FAQ analysis. Also not wrapped: roster import, admin resume.

VPS unit `systemd/bale-mcp.service` and Compose profile `mcp` are opt-in. `deploy.yml` does not install them.
