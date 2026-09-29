# Admin panel (web UI — no terminal needed)

```powershell
cd $HOME\bale-adapter
. .\scripts\activate.ps1
python scripts\panel.py                 # http://127.0.0.1:8090
```

Set secrets in `/opt/bale-adapter/.env.secrets`:

```bash
BALE_PANEL_TOKEN=$(openssl rand -hex 24)      # signing secret (server-only)
BALE_PANEL_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | head -c 24)
BALE_PANEL_USER=admin
```

Public URL: **https://bale-adaptor.boostsho.ir/login** — sign in with **username + password** (not the signing token).

Local dev:

```powershell
$env:BALE_PANEL_TOKEN = "local-signing-secret-min-12-chars"
$env:BALE_PANEL_PASSWORD = "your-dev-password"
python scripts\panel.py
```

Or skip login locally only:

```powershell
python scripts\panel.py --no-auth
```

After login:

- **ارسال پیام** — one box for names (one per line / comma / space), one box for
  the message text; the preview checkbox resolves names without sending, then
  **تأیید و ارسال** sends for real.
- **دفترچه** — search, add a missing person manually (`NAME` + `chat_id`/phone),
  remove, or refresh everything from Bale.
- **صندوق / پیام‌ها / تحلیل / سیستم** — unread per agent and per chat, every stored
  message, concern buckets, KB facts and the runner log.

## On the VPS

`bale-panel.service` listens on `127.0.0.1:8090`; nginx serves the panel on **https://bale-adaptor.boostsho.ir**.

```bash
# secrets in /opt/bale-adapter/.env.secrets (see above)
systemctl restart bale-panel
```

Never share `BALE_PANEL_TOKEN` — it is not the login password. The panel can send as the company Bale account; use a strong `BALE_PANEL_PASSWORD`.

Design details: [.ai/design/panel.md](../design/panel.md).
