# Bale adapter API behind Cloudflare

Public URL: **https://bale-adaptor.boostsho.ir** → nginx on staging VPS → `127.0.0.1:8787`.

## 1. Cloudflare DNS (required once)

In zone **boostsho.ir**:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `bale-adaptor` | `5.42.223.209` | **Proxied** (orange cloud) |

## 2. Cloudflare SSL/TLS

Until a publicly trusted or [Origin CA](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/) cert is on the VPS, set encryption mode to **Full** (not strict). After installing Origin CA or Let's Encrypt on the origin, use **Full (strict)**.

Recommended: **SSL/TLS → Overview → Full (strict)** with an **Origin Certificate** (hostnames: `bale-adaptor.boostsho.ir`) installed at:

- `/etc/nginx/ssl/bale-adaptor.boostsho.ir.crt`
- `/etc/nginx/ssl/bale-adaptor.boostsho.ir.key`

Enable **Always Use HTTPS** and **Minimum TLS 1.2** in the Cloudflare dashboard.

## 3. Install nginx on the VPS

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
