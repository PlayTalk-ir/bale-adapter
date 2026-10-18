# Environment variables

Set automatically by `activate.ps1` / `activate.sh` for local dev.

| Variable | Local default | Purpose |
|----------|---------------|---------|
| `BALE_SESSION_PATH` | `.session/session.bale` | aiobale session |
| `BALE_KB_DIR` | `kb/` | KB output |
| `BALE_LOG_FILE` | `logs/userbot.log` | Logs |
| `BALE_STORE_PATH` | `data/support_inbox.sqlite` | Inbox DB |
| `BALE_CONTACTS_PATH` | `data/contacts.sqlite` | Local contact book |
| `BALE_OBSERVE_ONLY` | `true` | No auto-reply |
| `BALE_API_ENABLED` | `false` | HTTP API + outbox worker |
| `BALE_ADAPTER_API_TOKENS` | _(empty)_ | Comma-separated API bearer tokens — **`.env.secrets` only** (reloaded live by the API) |
| `BALE_SECRETS_FILE` | `.env.secrets` | Path to secrets file (VPS: `/opt/bale-adapter/.env.secrets`) |
| `BALE_OUTBOX_PATH` | `data/outbox.sqlite` | Outbound queue DB |
| `BALE_PHONE_PEPPER` | _(empty)_ | Phone cache HMAC (set in `.env.secrets` on VPS) |
| `PYTHONIOENCODING` | `utf-8` (Windows) | Emoji in login |
| `PYTHONPATH` | repo root | Imports |
| `BALE_PANEL_TOKEN` | (not set) | Cookie/CSRF signing secret (server-only; deploy auto-generates) |
| `BALE_PANEL_PASSWORD` | (not set) | Operator login password (required, min 8 chars) |
| `BALE_PANEL_USER` | `admin` | Login username |

Full API/outbox knobs: [docs/api.md](../../docs/api.md).

## MCP server (optional)

Not set by `activate.sh`. The MCP process is a client of the HTTP API. See [docs/mcp.md](../../docs/mcp.md).

| Variable | Default | Purpose |
|----------|---------|---------|
| `BALE_MCP_API_BASE_URL` | `http://127.0.0.1:8787` | Adapter origin |
| `BALE_MCP_API_TOKEN` | _(required)_ | Bearer token for that API — **not in git** |
| `BALE_MCP_HTTP_HOST` | `127.0.0.1` | Streamable HTTP bind |
| `BALE_MCP_HTTP_PORT` | `8790` | Streamable HTTP port |
| `BALE_MCP_HTTP_ALLOW_REMOTE` | `false` | Allow a non-loopback bind |
| `BALE_MCP_TIMEOUT_S` | `30` | Per-request timeout |

Production values: `.ai/architecture/deploy.md`
