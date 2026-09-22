# Architecture overview

> Human-maintained. AI agents: read only.

## Purpose

Bale userbot adapter (Shape C) for PlayTalk's **shared company Bale account**.
Runs on VPS `130.185.76.124` alongside `nexa-backend` as `bale-platform.service`.

## VPS layout

```
/opt/bale-adapter/
├── .session/session.bale      # aiobale session (0600) — never in git
├── data/support_inbox.sqlite  # per-agent inbox cache — never in git
├── venv/
├── bale_platform/             # adapter + CLI modules
├── kb/learn.py                # structured fact extraction
├── scripts/support_cli.py     # AI-facing CLI
├── scripts/login.py           # one-time OTP login (console only)
└── .env                       # BALE_* paths
```

## Local dev layout

Same structure under the git clone; `venv/` managed by `uv` via `pyproject.toml`.

## Key processes

| Process | Entry | Role |
|---------|-------|------|
| Listener | `python -m bale_platform.runner` | Real-time observe + store |
| Support CLI | `python scripts/support_cli.py` | Agent-driven inbox/send/analyze |
| Login | `python scripts/login.py` | Human-only OTP |
