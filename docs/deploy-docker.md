# Docker deployment (Laravel VPS)

Run **bale-adapter** as a Compose service on the same external Docker network as Steach/Laravel. Laravel calls `http://bale-adapter:8787` — **no host port** is published.

> **One session only:** Bale allows a single active userbot session per account. Stop the legacy **systemd** `bale-platform.service` (and any other host using the same session) before starting Docker. Do not run `support_cli.py` on the host against the same session file; use `docker compose exec` inside this stack instead.

## Prerequisites

- Docker Engine + Compose v2 on the VPS
- Existing Laravel stack with a named bridge network (e.g. `steach_laravel`)
- Git clone of this repo on the server (or pull the image you build in CI)

## First-time setup

1. **Clone and enter the repo** (example path):

   ```bash
   cd /opt/bale-adapter
   ```

2. **Stop conflicting deployments:**

   ```bash
   systemctl stop bale-platform.service   # if previously on systemd
   ```

3. **Configure env files:**

   ```bash
   cp .env.example .env
   cp .env.secrets.example .env.secrets
   chmod 600 .env.secrets
   ```

4. **Set the Laravel network name** in `.env`:

   ```bash
   # Must match: docker network ls
   LARAVEL_DOCKER_NETWORK=steach_laravel
   ```

5. **Generate API secrets** (paste output into `.env.secrets`):

   ```bash
   ./scripts/generate-docker-secrets.sh
   ```

   Required secrets:

   | Variable | Purpose |
   |----------|---------|
   | `BALE_ADAPTER_API_TOKENS` | Bearer token(s) for Laravel (`Authorization: Bearer …`) |
   | `BALE_PHONE_PEPPER` | Stable HMAC key for phone cache entries |

6. **Build and start** (API comes up even before login — `/healthz` stays green; `/readyz` shows `session_connected: false` until you log in):

   ```bash
   docker compose build
   docker compose up -d
   ```

   After `docker compose run ... login.py` writes the session to the `bale_session` volume, the runner reconnects automatically (no restart required).

## One-time Bale login (OTP)

Session is stored on the **`bale_session`** volume at `/app/.session/session.bale`.

```bash
docker compose run --rm -it bale-adapter python scripts/login.py
```

- Enter phone and OTP **only in the terminal** (never in chat/CI).
- Runs as the same `app` user (uid 1000) as the long-running service.
- After success, start the service: `docker compose up -d`.

## Verify from the Laravel network

Pick a running Laravel container on the same network:

```bash
LARAVEL_CONTAINER=steach-app   # example name
TOKEN='your-token-from-env-secrets'

# Health (no auth)
docker exec "$LARAVEL_CONTAINER" curl -sf http://bale-adapter:8787/healthz

# Ready (auth)
docker exec "$LARAVEL_CONTAINER" curl -sf \
  -H "Authorization: Bearer $TOKEN" \
  http://bale-adapter:8787/readyz

# Queue a message (dry_run — no Bale send; stays paused by default)
docker exec "$LARAVEL_CONTAINER" curl -sf -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"recipient":{"bale_user_id":"123"},"text":"test","idempotency_key":"docker-smoke:1"}' \
  http://bale-adapter:8787/v1/messages
```

Expect `202` with `status: queued`. With `BALE_SEND_MODE=dry_run` and `BALE_SENDING_PAUSED=true`, the worker does not perform live sends.

## Safe defaults (shipping config)

`.env.example` sets:

| Variable | Value | Effect |
|----------|-------|--------|
| `BALE_API_ENABLED` | `true` | API + outbox worker in runner |
| `BALE_API_HOST` | `0.0.0.0` | Listen inside container (not on host) |
| `BALE_SENDING_PAUSED` | `true` | Kill switch — intake may return `503 sending_paused` |
| `BALE_SEND_MODE` | `dry_run` | Worker never calls Bale `send_message` |
| `BALE_OBSERVE_ONLY` | `true` | Userbot does not auto-reply |

Sending stays off until you complete **Go live** below.

## Go live (later)

1. Edit `.env`:

   ```bash
   BALE_SEND_MODE=live
   BALE_SENDING_PAUSED=false
   ```

2. Restart:

   ```bash
   docker compose up -d --force-recreate
   ```

   Or clear only the circuit breaker (if tripped) without changing env:

   ```bash
   curl -X POST -H "Authorization: Bearer $TOKEN" http://bale-adapter:8787/v1/admin/resume
   ```

   (Run `curl` from a container on the same network, as above.)

3. Confirm `readyz` shows `paused: false` and `send_mode: live`.

4. Monitor logs:

   ```bash
   docker compose logs -f --tail=100 bale-adapter
   ```

## Operator support CLI

Use the running container — do not open a second session on the host:

```bash
docker compose exec bale-adapter python scripts/support_cli.py inbox --unread
docker compose exec bale-adapter python scripts/support_cli.py send --to 09xxxxxxxxx --text "…" --dry-run
```

## Volumes

| Volume | Mount | Contents |
|--------|-------|----------|
| `bale_session` | `/app/.session` | aiobale `session.bale` |
| `bale_data` | `/app/data` | outbox + support inbox SQLite |
| `bale_kb` | `/app/kb` | learned facts |
| `bale_logs` | `/app/logs` | `userbot.log` |

Log rotation uses the Compose `json-file` driver (`max-size` / `max-file` in `docker-compose.yml`).

## Systemd path (unchanged)

Bare-metal deploy via `systemd/bale-platform.service` and `.github/workflows/deploy.yml` is still supported. Use **either** systemd **or** Docker for the same Bale account, not both.

## Operator env checklist

**`.env` (required):**

- `LARAVEL_DOCKER_NETWORK` — external network name
- `BALE_SESSION_PATH`, `BALE_STORE_PATH`, `BALE_OUTBOX_PATH`, `BALE_KB_DIR`, `BALE_LOG_FILE` — use `.env.example` paths
- `BALE_API_ENABLED=true`, `BALE_API_HOST=0.0.0.0`, `BALE_API_PORT=8787`
- `BALE_OBSERVE_ONLY`, `BALE_SENDING_PAUSED`, `BALE_SEND_MODE` — start safe; change for go-live

**`.env.secrets` (required when API enabled):**

- `BALE_ADAPTER_API_TOKENS`
- `BALE_PHONE_PEPPER`
