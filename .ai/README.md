# AI agent documentation

Read this folder before operating on the PlayTalk Bale account.

## Session lifecycle

| File | When |
|------|------|
| [startup.md](startup.md) | Start of every AI session |
| [shutdown.md](shutdown.md) | End of every AI session |

## Folders

| Folder | Owner | Purpose |
|--------|-------|---------|
| [architecture/](architecture/README.md) | **Human only** — agents must not edit | System layout, constraints, deploy topology |
| [design/](design/README.md) | AI-maintained | Implementation design, data flows, trade-offs |
| [capabilities/](capabilities/README.md) | AI + human | What agents can do via CLI |
| [integrations/](integrations/README.md) | AI-maintained | Cursor, Claude, Cline, Qoder |
| [setup/](setup/README.md) | Human + AI | Install and daily ops for support staff |
| [prompts/](prompts/README.md) | Human + AI | Copy-paste prompts |

## Entry point for agents

1. Read `startup.md`
2. Read `capabilities/README.md`
3. Read `design/inbox-store.md` if handling unread/ack
4. Never read or modify OTP/session files
