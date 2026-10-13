# Bale adapter HTTP API (v1)

Authenticated JSON API for queueing outbound Bale messages from the shared PlayTalk support userbot. Enabled only when `BALE_API_ENABLED=true` on the runner process.

## Base URL

Default bind: `http://127.0.0.1:8787` (`BALE_API_HOST`, `BALE_API_PORT`). Expose beyond localhost via reverse proxy (nginx) with TLS; terminate auth at the adapter.

**Interactive docs (Swagger UI):** `GET /v1/docs` — sign in with the **same username and password as the admin panel** (`BALE_PANEL_USER`, usually `admin`, and `BALE_PANEL_PASSWORD`). If you are already logged into the panel in the same browser, the docs open without prompting again. OpenAPI schema at `GET /v1/openapi.json` (same session). Staging: **https://bale-adaptor.boostsho.ir/v1/docs**

## Authentication

All endpoints except `GET /healthz` require:

```
Authorization: Bearer <token>
```

Tokens are validated on each API request. Configure them either way:

1. **Admin panel** — **توکن API** (`/api-tokens`): create labeled tokens; the full secret is shown once. Stored as SHA-256 hashes in `data/api_tokens.json` (`BALE_API_TOKENS_PATH`).
2. **Environment** — comma-separated list in `BALE_ADAPTER_API_TOKENS` (plaintext in `.env.secrets`; survives deploy, not revocable from the panel).

Both sources are accepted. Constant-time comparison; supports rotation.

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

## `GET /v1/session`

Auth required. Bale links with a phone session file, so `qr` and `qr_data_url` are always `null`. `state` is `open` when the userbot is connected.

```json
{
  "state": "open",
  "connected": true,
  "qr": null,
  "qr_data_url": null,
  "me": null,
  "last_error": null,
  "updated_at": "2026-10-12T00:00:00+00:00"
}
```

## `GET /v1/inbox/events`

Auth required. Cursor feed of stored support-inbox messages (the route the support panel polls). Query: `after` (default `0`, exclusive seq) and `limit` (default `200`, max `1000`).

```json
{
  "events": [
    {
      "seq": 1,
      "chat_id": "100",
      "message_id": 10,
      "direction": "in",
      "kind": "text",
      "text": "hello",
      "date_ms": 1,
      "sender_id": "9",
      "chat": {"name": "", "username": "", "phone": "09121234567"}
    }
  ],
  "next_after": 1,
  "has_more": false
}
```

`next_after` is the last event's `seq`, or the request `after` when the page is empty. `has_more` is true when the page is full. Re-saving an existing message keeps its `seq`.

## `GET /v1/inbox/chats/{chat_id}/history`

Auth required. Same event objects, oldest first. Query: `limit` (default `100`, max `500`).

## `POST /v1/messages`

Queue one or more messages for delivery (same `text`, `meta`, and `ttl_seconds` for every recipient).

### Request body

Single recipient:

```json
{
  "recipient": {"phone": "09xxxxxxxxx"},
  "text": "message body",
  "idempotency_key": "rule_bale:12:34",
  "meta": {"rule_id": 12, "campaign": "welcome"},
  "ttl_seconds": 86400
}
```

Multiple recipients (up to 50):

```json
{
  "recipients": [
    {"phone": "09924466793"},
    {"bale_user_id": "42"}
  ],
  "text": "message body",
  "idempotency_key": "rule_bale:12:34",
  "meta": {"rule_id": 12},
  "ttl_seconds": 604800
}
```

Use **`recipient`** or **`recipients`**, not both. Duplicate phones/user IDs in one request are rejected.

**Recipient object** — exactly one of:

| Field | Rules |
|-------|--------|
| `phone` | Iranian mobile; normalized to `989XXXXXXXXX` (`09…`, `9…`, `+98…`, `0098…`) |
| `bale_user_id` | Decimal digits only |
| `username` | Leading `@` stripped |

**`text`** — 1–4000 characters.

**`idempotency_key`** — required. A **stable id you choose** so retries do not create duplicate sends.

- Single `recipient`: the key is stored as-is (e.g. `rule_bale:12:34`).
- `recipients` array: each row gets a derived key `{idempotency_key}:{recipient}` (e.g. `rule_bale:12:34:phone_98924466793`). Look up status with `GET /v1/messages?idempotency_key=` using that per-recipient key, or the `idempotency_key` returned in the batch response.
- Safe to retry on network errors: same key + same text + same recipient(s) → **200** with existing queue rows; same key + different text/recipient → **409** `idempotency_conflict`.
- Format: 1–128 chars from `[A-Za-z0-9:_.-]`. Typical pattern: `rule_bale:<rule_id>:<event_id>` from Laravel.

**`meta`** — optional JSON object (≤ 2KB). **Stored in the outbox SQLite only** (`meta_json`); it is **not** sent to Bale and **not** shown in `GET /v1/messages` responses today. Use it to attach caller context (rule id, user id, ticket id) for your own reconciliation or future tooling.

**`ttl_seconds`** — optional; default `BALE_DEFAULT_TTL_S` (86400), max 7 days.

**`mode`** — optional, `send` (default) or `reply`. Reply mode is for answering someone who wrote to us (the support inbox):

- recipient must be `bale_user_id`
- that user must have sent us a message within `BALE_REPLY_WINDOW_H` (default 24h), otherwise `422 reply_window_closed`
- paced as a live conversation (`BALE_REPLY_*` below) instead of the outreach caps; quiet hours are skipped; global hourly/daily caps and the circuit breaker still apply
- once sent, the reply is written to the support inbox store, so it shows up in `/v1/inbox/events`

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

Success body (single `recipient`):

```json
{
  "message_id": "<ULID>",
  "status": "queued",
  "idempotency_key": "rule_bale:12:34"
}
```

Success body (`recipients` array, **202** or **200** on replay):

```json
{
  "idempotency_key": "rule_bale:12:34",
  "messages": [
    {
      "message_id": "<ULID>",
      "status": "queued",
      "idempotency_key": "rule_bale:12:34:phone_98924466793",
      "recipient": {"type": "phone", "masked": "98912***6793"}
    }
  ]
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

## `GET /v1/inbox/events?after=<seq>&limit=200`

Auth required. Private-chat messages from the support inbox store, oldest first, after a cursor. Consumers (the tech-support unified inbox) keep `next_after` and poll again with it. Every stored message gets a monotonic `seq` when first seen; edits and history re-syncs keep the original `seq`, so nothing is replayed.

```json
{
  "events": [
    {
      "seq": 812,
      "chat_id": "123456",
      "message_id": 99,
      "direction": "in",
      "kind": "text",
      "text": "سلام، کلاس امروز ساعت چنده؟",
      "date_ms": 1760000000000,
      "sender_id": "123456",
      "chat": {"name": "Sara Ahmadi", "username": "", "phone": null}
    }
  ],
  "next_after": 812,
  "has_more": false
}
```

`kind`: `text`, `photo`, `video`, `voice`, `audio`, `file`, `sticker`, `gift`. Media without a caption carries a Persian placeholder in `text` (e.g. `[پیام صوتی]`); media bytes are not exposed. `chat.name` comes from the sender's Bale profile (looked up once per chat) or the local contact book.

`chat.phone` is set when that Bale user id was resolved from an Iranian mobile via the outbox (`POST /v1/messages` with `recipient.phone`, class outreach, etc.). It is stored in the outbox DB as `989XXXXXXXXX` and returned as `09XXXXXXXXX` for roster matching in the support panel. Bale does not expose arbitrary inbound contacts' numbers; chats that only messaged support first stay `phone: null` until outreach or a manual match in the panel.

## `GET /v1/inbox/chats/{chat_id}/history?limit=100`

Auth required. Last `limit` stored messages of one chat, oldest first, same event shape. Used to backfill a conversation the first time it is opened.

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
| `BALE_API_RECORD_IN_INBOX` | `false` | Mirror non-reply API sends into support inbox DB (replies are always mirrored) |
| `BALE_REPLY_WINDOW_H` | `24` | Reply mode allowed only within this many hours of the user's last message |
| `BALE_REPLY_GLOBAL_MIN_INTERVAL_S` | `1.5` | Global min gap before a reply |
| `BALE_REPLY_JITTER_S` | `1.5` | Random extra delay for replies |
| `BALE_REPLY_MIN_INTERVAL_S` | `3` | Per-recipient min gap between replies |
| `BALE_REPLY_MAX_PER_HOUR` | `60` | Per-recipient hourly reply cap |
