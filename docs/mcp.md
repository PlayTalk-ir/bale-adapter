# MCP server

Optional [Model Context Protocol](https://modelcontextprotocol.io) server so Cursor, Claude Desktop, and other MCP clients can use the shared PlayTalk Bale account.

The server is a client of the adapter HTTP API. It sends `Authorization: Bearer <token>` and returns API JSON unchanged. It does **not** open `.session/session.bale`, the inbox database, or the outbox database, so outbox rate limits, privacy rules, and audit behaviour stay in the adapter.

Install the SDK (the adapter service does not need it; it is the `mcp` extra in `pyproject.toml`):

```bash
pip install 'mcp>=2,<3'
```

On mcp 2.x the SDK class formerly called FastMCP is `MCPServer` (`mcp.server.mcpserver`). This server uses that class.

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `BALE_MCP_API_BASE_URL` | `http://127.0.0.1:8787` | Adapter origin, no `/v1` suffix |
| `BALE_MCP_API_TOKEN` | _(required)_ | One API bearer token |
| `BALE_MCP_HTTP_HOST` | `127.0.0.1` | Streamable HTTP bind address |
| `BALE_MCP_HTTP_PORT` | `8790` | Streamable HTTP port (`/mcp`) |
| `BALE_MCP_HTTP_ALLOW_REMOTE` | `false` | Set `true` to allow a non-loopback bind |
| `BALE_MCP_TIMEOUT_S` | `30` | HTTP timeout per API call |

The HTTP listener has no auth of its own and holds the API token, so it refuses to bind anything other than loopback unless `BALE_MCP_HTTP_ALLOW_REMOTE=true`.

Do not commit the token. Do not put it in the base URL.

## Issue a token

The MCP process needs the plaintext bearer. The adapter stores panel tokens as hashes.

1. Sign in to the admin panel and open **توکن API** (`/api-tokens`).
2. Create a token labeled `mcp`. The secret is shown once.
3. Put it in the MCP environment as `BALE_MCP_API_TOKEN`.

The runner reloads panel tokens immediately. Alternatively, add one dedicated value to `BALE_ADAPTER_API_TOKENS` in `.env.secrets` (comma-separated, plaintext, not revocable from the panel) and copy that same value into `BALE_MCP_API_TOKEN`. Use a token for MCP only, not one shared with another app if you can avoid it.

The adapter API must be running (`BALE_API_ENABLED=true`). See [api.md](api.md).

## Run

Use the adapter virtualenv (`source scripts/activate.sh`, or `/opt/bale-adapter/venv/bin/python` on the VPS). Importing `bale_platform` loads the adapter stack, so `aiobale` has to be installed there; the MCP process still only calls HTTP. From the repo root:

```bash
export BALE_MCP_API_BASE_URL=http://127.0.0.1:8787
export BALE_MCP_API_TOKEN=replace-with-api-token

# stdio — for desktop clients that spawn a process
python -m bale_platform.mcp_server
python scripts/mcp_server.py

# streamable HTTP on 127.0.0.1:8790, path /mcp
python -m bale_platform.mcp_server http
python scripts/mcp_server.py http --port 8790
```

## Tools

| Tool | API | Notes |
|------|-----|--------|
| `adapter_health` | `GET /healthz` | Process is up |
| `adapter_ready` | `GET /readyz` | Session, queue depth, pause, send mode |
| `session_status` | `GET /v1/session` | `qr` is always null |
| `list_inbox` | `GET /v1/inbox/events` | Shared private-chat feed, not per-agent unread |
| `read_chat` | `GET /v1/inbox/chats/{chat_id}/history` | Does not mark read |
| `search_contacts` | `GET /v1/contacts` | Full book, filtered locally |
| `message_status` | `GET /v1/messages/...` | Phones stay masked |
| `send_message` | `POST /v1/messages` | Queues **one** outbox row |

`send_message` is annotated `readOnlyHint=false`, `destructiveHint=true`, `idempotentHint=false`, `openWorldHint=true`. Clients should ask for confirmation. The call does not deliver the Bale message itself: the outbox worker does, under the existing rate limits and `BALE_SEND_MODE`. Pass a stable `idempotency_key` and reuse it if you retry the same send.

Read tools are annotated read-only. They do not ack chats.

## Not exposed (needs an API decision)

These exist on the CLI or in local files. There is no HTTP route, and the MCP server does not read SQLite or the session to imitate them.

| Wanted capability | Today | Gap |
|-------------------|--------|-----|
| Per-agent unread | `support_cli.py inbox --agent` | No route. `GET /v1/inbox/events` is a shared seq cursor, not `agent_acks`. |
| Mark read / ack | `support_cli.py ack` | No route. Acks are written only in the inbox store. |
| KB facts | `kb/learned_facts.mdl` | No route. |
| FAQ topics | `analyze` / `collect` | No route. `analysis.py` runs on the local inbox DB. |

Also left unexposed on purpose: `POST /v1/contacts/import-roster` (live Bale lookups) and `POST /v1/admin/resume` (clears the circuit breaker). `POST /v1/messages` accepts up to 50 recipients; `send_message` allows one so confirmation is about a single person.

A future API could add, for example, `GET /v1/inbox/unread?agent=`, `POST /v1/inbox/ack`, `GET /v1/kb/facts`, and `GET /v1/analysis/faq`. Those are not implemented.

## Cursor

stdio (project `.cursor/mcp.json` or Cursor Settings → MCP):

```json
{
  "mcpServers": {
    "bale-adapter": {
      "command": "python",
      "args": ["-m", "bale_platform.mcp_server"],
      "env": {
        "BALE_MCP_API_BASE_URL": "http://127.0.0.1:8787",
        "BALE_MCP_API_TOKEN": "replace-with-api-token"
      }
    }
  }
}
```

Run that from the repo root, or set `cwd` / `PYTHONPATH` so `bale_platform` imports. If the adapter is already on the host, point `BALE_MCP_API_BASE_URL` at it.

Streamable HTTP, after `python -m bale_platform.mcp_server http`:

```json
{
  "mcpServers": {
    "bale-adapter": {
      "url": "http://127.0.0.1:8790/mcp"
    }
  }
}
```

## Claude Desktop

`claude_desktop_config.json` (stdio):

```json
{
  "mcpServers": {
    "bale-adapter": {
      "command": "python",
      "args": ["-m", "bale_platform.mcp_server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/bale-adapter",
        "BALE_MCP_API_BASE_URL": "http://127.0.0.1:8787",
        "BALE_MCP_API_TOKEN": "replace-with-api-token"
      }
    }
  }
}
```

Use the venv interpreter as `command` if `python` is not the repo environment. Claude's HTTP MCP form is the same URL as Cursor: `http://127.0.0.1:8790/mcp`.

## Opt-in on the VPS

`deploy.yml` does not install or start this. The adapter unit is unchanged.

One-time, after the adapter venv exists:

```bash
cd /opt/bale-adapter
./scripts/bootstrap-mcp.sh
# add BALE_MCP_API_TOKEN=... to /opt/bale-adapter/.env.secrets
install -m 0644 systemd/bale-mcp.service /etc/systemd/system/bale-mcp.service
systemctl daemon-reload
systemctl enable --now bale-mcp.service
```

`bale-mcp.service` listens on `127.0.0.1:8790` and calls `http://127.0.0.1:8787`. Reach it with an SSH tunnel if a laptop client needs it. Leave the unit disabled if you only use stdio on a workstation.

### Docker Compose profile

The default `docker compose up` still starts only `bale-adapter`. The MCP sidecar is profile `mcp` and is not part of the adapter image CI builds:

```bash
# BALE_MCP_API_TOKEN in .env.secrets
docker compose --profile mcp up -d --build bale-mcp
```

Inside that container the API base URL is `http://bale-adapter:8787` and the MCP port binds to `127.0.0.1:8790` (not published on the host).
