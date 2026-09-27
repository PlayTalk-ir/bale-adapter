# HTTP API + outbox

When `BALE_API_ENABLED=true`, the runner starts an aiohttp server and an outbox worker sharing the same aiobale client (`run_in_background=True`).

- Contract: [docs/api.md](../../docs/api.md)
- Queue DB: `BALE_OUTBOX_PATH` (WAL SQLite)
- CLI `send` and API share `RecipientResolver` + phone cache in the outbox DB
