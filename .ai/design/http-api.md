# HTTP API + outbox

When `BALE_API_ENABLED=true`, the runner starts an aiohttp server and an outbox worker sharing the same aiobale client (`run_in_background=True`).

- Contract: [docs/api.md](../../docs/api.md)
- Queue DB: `BALE_OUTBOX_PATH` (WAL SQLite)
- CLI `send` and API share `RecipientResolver` + phone cache in the outbox DB
- Recipient lookup uses aiobale-py 0.3.8: `search_contact(phone_number)`, `search_username` → `.user`, `send_message(..., message_id=...)`
- VPS systemd bootstrap installs `python-ulid` with the other runner deps; first start timeout is 180s.
- Staging public URL (Cloudflare proxied): `https://bale-adaptor.boostsho.ir` → nginx → `127.0.0.1:8787`. Setup: [docs/nginx-cloudflare.md](../../docs/nginx-cloudflare.md).
- Swagger UI at `/v1/docs` (Basic auth: `BALE_PANEL_USER` + `BALE_PANEL_PASSWORD`, same as panel login). OpenAPI at `/v1/openapi.json`.
