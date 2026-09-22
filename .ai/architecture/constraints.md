# Architecture constraints

> Human-maintained. AI agents: read only.

## Shared Bale account

- Sales, education, technical, and teacher support share **one login**.
- Bale `unread_count` is **account-wide** — reading in the app clears for everyone.
- Per-agent unread is implemented in software (`data/support_inbox.sqlite`), not by Bale.

## Why aiobale (not Bale Bot API)

- Bot API only sees messages where the bot is mentioned.
- PlayTalk needs **all** customer messages in company chats.
- `aiobale-py` logs in as the company user via session file.

## Rate limits

- aiobale is unofficial; avoid tight loops of API calls.
- Runner is observe-only; sends go only through explicit `support_cli.py send`.

## Security

- OTP: terminal only (`getpass`), never logs, never AI chat.
- Session: `.session/` mode 0600, never commit.
- Corporate account only — not personal numbers.

## Privacy stores

| Store | Content |
|-------|---------|
| `kb/learned_facts.mdl` | Structured facts, PII-filtered |
| `data/support_inbox.sqlite` | Message cache for support tools — local/VPS only |
