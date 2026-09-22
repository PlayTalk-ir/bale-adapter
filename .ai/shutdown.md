# AI session shutdown

Run before ending a support AI session.

## 1. Ack handled chats

For every conversation the human fully handled this session:

```bash
python scripts/support_cli.py ack --agent AGENT_ID --chat CHAT_ID --message-id MSG_ID
```

## 2. Note open items

If chats remain unanswered, tell the human:
- chat id, last message snippet, suggested next action

## 3. Update design docs (if needed)

If you changed behavior or learned a non-obvious pattern, update `.ai/design/`
— **not** `.ai/architecture/`.

## 4. Do not save to git

Never commit or stage:
- `.session/`
- `data/support_inbox.sqlite`
- `.env`
- OTP or message content in markdown

## 5. Optional handoff line for human

```
Session end: N chats acked, M still unread for AGENT_ID.
Runner: [running | stopped — run python -m bale_platform.runner]
```
