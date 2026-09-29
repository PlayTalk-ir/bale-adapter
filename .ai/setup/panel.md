# Admin panel (web UI — no terminal needed)

```powershell
cd $HOME\bale-adapter
. .\scripts\activate.ps1
python scripts\panel.py                 # http://127.0.0.1:8090
```

A random operator token is printed at startup; or pin one:

```powershell
$env:BALE_PANEL_TOKEN = "<strong random string>"
python scripts\panel.py --port 9000
```

Login with that token, then:

- **ارسال پیام** — one box for names (one per line / comma / space), one box for
  the message text; the preview checkbox resolves names without sending, then
  **تأیید و ارسال** sends for real.
- **دفترچه** — search, add a missing person manually (`NAME` + `chat_id`/phone),
  remove, or refresh everything from Bale.
- **صندوق / پیام‌ها / تحلیل / سیستم** — unread per agent and per chat, every stored
  message, concern buckets, KB facts and the runner log.

## On the VPS (loopback + SSH tunnel)

`systemd/bale-panel.service` binds `127.0.0.1:8090` on purpose:

```bash
echo "BALE_PANEL_TOKEN=$(openssl rand -hex 24)" >> /opt/bale-adapter/.env
install -m 0644 systemd/bale-panel.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now bale-panel
ssh -L 8090:127.0.0.1:8090 root@VPS      # then http://127.0.0.1:8090
```

Never expose the panel directly to the internet; the token is the only gate
and it can send messages as the company account.

## Local development without login

```powershell
python scripts\panel.py --no-auth        # skip login — local dev only
```

Design details: [.ai/design/panel.md](../design/panel.md).
