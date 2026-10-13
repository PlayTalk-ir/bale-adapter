# Bale adapter API behind Cloudflare

Public URL: **https://bale-adaptor.boostsho.ir** → nginx on staging VPS → `127.0.0.1:8787`.

## 1. Cloudflare DNS (required once)

In zone **boostsho.ir** (or run from repo root after fixing `CLOUDFLARE_API_TOKEN` in `j:/dev/minecraft/.env.cloudflare`):

```powershell
j:\dev\minecraft\scripts\cloudflare-dns-bale-adaptor.ps1
```

Manual dashboard alternative:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `bale-adaptor` | `5.42.223.209` | **DNS only** (grey cloud) for staging; see §2 for orange cloud |

## 2. Cloudflare SSL/TLS

Origin uses **Let's Encrypt** (`certbot` webroot → `/etc/letsencrypt/live/bale-adaptor.boostsho.ir/`).

### Proxied (orange cloud) — 525 on this VPS

Cloudflare’s network often **cannot complete TLS to the origin on port 443** (error **525**), while direct clients to `5.42.223.209:443` work fine. nginx therefore serves the app on **port 80** as well (see `deploy/nginx/bale-adaptor.boostsho.ir.conf`).

To use **proxied** DNS, set Cloudflare **SSL/TLS → Overview → Encryption mode** to **Flexible** (edge HTTPS → origin HTTP :80). The API token in `.env.cloudflare` can edit DNS but may not change SSL mode (403); use the dashboard if needed.

Alternative long-term fixes: **Cloudflare Tunnel** (`cloudflared`) or **DNS only** (grey cloud).

### DNS only (grey cloud) — recommended for staging now

Set the `bale-adaptor` A record to **DNS only** (grey cloud). Clients connect directly to the origin with Let’s Encrypt on **443**.

Also enable **Always Use HTTPS** and **Minimum TLS 1.2** in the Cloudflare dashboard when using proxied mode.

## 3. nginx routing (same hostname)

| Path | Upstream |
|------|----------|
| `/healthz`, `/readyz`, `/v1/*` | Bale HTTP API (`127.0.0.1:8787`) — includes `/v1/docs` (panel password login) |
| `/`, `/login`, `/send`, `/contacts`, … | Admin panel (`127.0.0.1:8090`) |

Install configs from `deploy/nginx/` on the VPS. Ensure `bale-panel.service` is enabled (deploy workflow installs it).

## 4. Install nginx on the VPS

From the repo on the server (or copy files from `deploy/nginx/`):

```bash
install -d /etc/nginx/snippets /var/www/certbot /etc/nginx/ssl
install -m 0644 deploy/nginx/snippets/cloudflare-realip.conf /etc/nginx/snippets/
install -m 0644 deploy/nginx/snippets/cloudflare-allow.conf /etc/nginx/snippets/
install -m 0644 deploy/nginx/bale-adaptor.boostsho.ir.conf /etc/nginx/sites-available/
ln -sf /etc/nginx/sites-available/bale-adaptor.boostsho.ir.conf /etc/nginx/sites-enabled/
```

On **steach-stage-vps**, install the host catch-all first so unknown hostnames never proxy to Bale (`vps-management/scripts/stage-nginx-default-catchall.sh`).

```bash
nginx -t && systemctl reload nginx
```

Origin TLS: self-signed (bootstrap) or `certbot certonly --nginx -d bale-adaptor.boostsho.ir` once DNS is live.

## 4. Security layers

- Bale API stays on **localhost**; only nginx is exposed on 443.
- nginx **allow Cloudflare IP ranges only** on 443 (`cloudflare-allow.conf`).
- UFW: **3939** (SSH), **80/443** (HTTP/S for Cloudflare → origin).
- API auth: **Bearer token** (`BALE_ADAPTER_API_TOKENS`) — Cloudflare does not replace this.

## 5. Verify

```bash
curl -sS https://bale-adaptor.boostsho.ir/healthz
# {"ok": true}

curl -sS -H "Authorization: Bearer $TOKEN" https://bale-adaptor.boostsho.ir/readyz
```

Laravel (or other backends) should use the public HTTPS URL and store the bearer token in app secrets, not in git.
