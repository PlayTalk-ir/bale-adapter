# Deploy

> Human-maintained. AI agents: read only.

## Automatic deploy

```bash
git push origin master
# → GitHub Actions: test, ssh VPS, git pull, systemctl restart bale-platform
```

## Missing session on VPS

```bash
ssh root@130.185.76.124
cd /opt/bale-adapter
source venv/bin/activate
python scripts/login.py
systemctl restart bale-platform.service
```

## Copy session from local (same account)

```bash
scp .session/session.bale root@130.185.76.124:/opt/bale-adapter/.session/session.bale
ssh root@130.185.76.124 'chmod 600 /opt/bale-adapter/.session/session.bale && systemctl restart bale-platform'
```

## Env vars (production)

| Variable | Value |
|----------|-------|
| `BALE_SESSION_PATH` | `/opt/bale-adapter/.session/session.bale` |
| `BALE_KB_DIR` | `/opt/bale-adapter/kb` |
| `BALE_LOG_FILE` | `/opt/bale-adapter/logs/userbot.log` |
| `BALE_STORE_PATH` | `/opt/bale-adapter/data/support_inbox.sqlite` |
| `BALE_OBSERVE_ONLY` | `true` |
