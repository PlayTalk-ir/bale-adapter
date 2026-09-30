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
| A | `bale-adaptor` | `5.42.223.209` | **Proxied** (orange cloud) |

## 2. Cloudflare SSL/TLS

Origin uses **Let's Encrypt** (`certbot` webroot → `/etc/letsencrypt/live/bale-adaptor.boostsho.ir/`). Set Cloudflare encryption to **Full (strict)**.

Also enable **Always Use HTTPS** and **Minimum TLS 1.2** in the Cloudflare dashboard.

## 3. nginx routing (same hostname)

| Path | Upstream |
|------|----------|
| `/healthz`, `/readyz`, `/v1/*` | Bale HTTP API (`127.0.0.1:8787`) — includes `/v1/docs` and `/v1/openapi.json` (Basic auth = panel password) |
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
