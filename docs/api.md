# Bale adapter HTTP API (v1)

Authenticated JSON API for queueing outbound Bale messages from the shared PlayTalk support userbot. Enabled only when `BALE_API_ENABLED=true` on the runner process.

## Base URL

Default bind: `http://127.0.0.1:8787` (`BALE_API_HOST`, `BALE_API_PORT`). Expose beyond localhost via reverse proxy (nginx) with TLS; terminate auth at the adapter.

## Authentication

All endpoints except `GET /healthz` require:

```
Authorization: Bearer <token>
```

Tokens are configured as a comma-separated list in `BALE_ADAPTER_API_TOKENS` (constant-time comparison; supports rotation).

## Common headers

Every response includes `X-Request-Id` (generated if omitted on the request).

Errors:

```json
{"error": {"code": "...", "message": "...", "details": {}}}
```

## `GET /healthz`

No auth. Returns `{"ok": true}`.

## `GET /readyz`

Auth required. Example:

```json
{
  "session_connected": true,
  "queue_depth": 3,
  "paused": false,
  "send_mode": "live"
}
```

## `POST /v1/messages`

Queue a message for delivery.

### Request body

```json
{
  "recipient": {"phone": "09xxxxxxxxx"},
  "text": "message body",
  "idempotency_key": "rule_bale:12:34",
  "meta": {"optional": "object"},
  "ttl_seconds": 86400
}
```

**Recipient** — exactly one of:

| Field | Rules |
|-------|--------|
| `phone` | Iranian mobile; normalized to `989XXXXXXXXX` (`09…`, `9…`, `+98…`, `0098…`) |
| `bale_user_id` | Decimal digits only |
| `username` | Leading `@` stripped |

**`text`** — 1–4000 characters.

**`idempotency_key`** — opaque 1–128 chars from `[A-Za-z0-9:_.-]`.

**`meta`** — optional JSON object, ≤ 2KB stored only (never sent to Bale).

**`ttl_seconds`** — optional; default `BALE_DEFAULT_TTL_S` (86400), max 7 days.

### Responses

| Status | Meaning |
|--------|---------|
| 202 | New message queued |
| 200 | Same `idempotency_key` and same payload (recipient + text hash) |
| 409 | Same key, different payload (`idempotency_conflict`) |
| 401 | Missing/invalid token |
| 422 | Validation (`recipient_invalid`, etc.) |
| 413 | `text_too_long` |
| 429 | Intake rate limit or queue full (`rate_limited`, `Retry-After`) |
| 503 | Kill switch or circuit breaker (`sending_paused`, `Retry-After`) |

Success body:

```json
{
  "message_id": "<ULID>",
  "status": "queued",
  "idempotency_key": "rule_bale:12:34"
}
```

## `GET /v1/messages/{message_id}`

## `GET /v1/messages?idempotency_key=...`

Status payload:

```json
{
  "message_id": "...",
  "idempotency_key": "...",
  "status": "queued|resolving|sending|sent|failed|expired|cancelled|delivery_unknown",
  "attempts": 0,
  "recipient": {"type": "phone", "masked": "98912***4567"},
  "bale_user_id": 123,
  "bale_message_id": 456,
  "error": {"code": "...", "message": "..."},
  "dry_run": false,
  "created_at": "2026-09-27T12:00:00+00:00",
  "sent_at": null,
  "updated_at": "2026-09-27T12:00:01+00:00"
}
```

Terminal error codes include: `recipient_not_found`, `recipient_not_on_bale`, `bale_error`, `session_invalid`, `expired`, `delivery_unknown`.

## `POST /v1/admin/resume`

Auth required. Clears the circuit breaker and resumes sending (does not clear `BALE_SENDING_PAUSED` env kill switch).

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BALE_API_ENABLED` | `false` | Enable API + outbox worker in runner |
| `BALE_API_HOST` | `127.0.0.1` | Bind address |
| `BALE_API_PORT` | `8787` | Bind port |
| `BALE_ADAPTER_API_TOKENS` | _(empty)_ | Comma-separated bearer tokens (required if API enabled) |
| `BALE_API_RATE_PER_MIN` | `60` | Intake limit per token per minute |
| `BALE_QUEUE_MAX` | `500` | Max active queue depth before 429 |
| `BALE_DEFAULT_TTL_S` | `86400` | Default message TTL |
| `BALE_OUTBOX_PATH` | `data/outbox.sqlite` | Outbox SQLite (WAL) |
| `BALE_SEND_MODE` | `live` | `live`, `dry_run`, or `resolve_only` |
| `BALE_SENDING_PAUSED` | `false` | Kill switch |
| `BALE_PHONE_PEPPER` | _(empty)_ | HMAC pepper for phone cache keys |
| `BALE_SEND_MIN_INTERVAL_S` | `8` | Global min gap between sends |
| `BALE_SEND_JITTER_S` | `7` | Random extra delay |
| `BALE_SEND_MAX_PER_HOUR` | `120` | Global hourly cap |
| `BALE_SEND_MAX_PER_DAY` | `600` | Global daily cap |
| `BALE_RECIPIENT_MIN_INTERVAL_S` | `60` | Per-recipient min gap |
| `BALE_RECIPIENT_MAX_PER_HOUR` | `5` | Per-recipient hourly cap |
| `BALE_RECIPIENT_MAX_PER_DAY` | `15` | Per-recipient daily cap |
| `BALE_NEW_PEER_MAX_PER_DAY` | `50` | Phone/username lookup budget |
| `BALE_LOOKUP_MIN_INTERVAL_S` | `5` | Min gap between lookups |
| `BALE_ALLOW_CONTACT_IMPORT` | `false` | Contact import on lookup |
| `BALE_QUIET_HOURS` | _(off)_ | e.g. `22:00-07:00` Asia/Tehran |
| `BALE_BREAKER_ERRORS` | `3` | Consecutive errors before pause |
| `BALE_API_RECORD_IN_INBOX` | `false` | Mirror API sends into support inbox DB |
