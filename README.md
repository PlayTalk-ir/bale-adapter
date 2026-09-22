# bale-adapter

ابزار اتصال **اکانت مشترک بله پلی‌تاک** به دستیارهای AI (Cursor، Claude، Cline، Qoder).
Support staff can send messages, read inbox, mine FAQ topics, and track per-agent unread.

Bale userbot adapter (Shape C) for PlayTalk — runs on VPS `130.185.76.124` as `bale-platform.service`.

---

## نصب سریع — ویندوز

```powershell
irm https://raw.githubusercontent.com/PlayTalk-ir/bale-adapter/master/scripts/install-windows.ps1 | iex
```

Git، Python (uv)، clone، و login — یک خط. OTP را فقط در ترمینال وارد کنید، نه در چت AI.

| ورودی | نرمال |
|-------|--------|
| `09924466793` | `989924466793` |

**پرامپت AI:** [.ai/prompts/ready-fa.md](.ai/prompts/ready-fa.md)

---

## Quick install — Linux / macOS

```bash
git clone https://github.com/PlayTalk-ir/bale-adapter.git
cd bale-adapter
chmod +x scripts/bootstrap-local.sh scripts/ensure-uv.sh
./scripts/bootstrap-local.sh
```

---

## مستندات AI — `.ai/`

**AI agents: read this folder first.**

| File / folder | Purpose |
|---------------|---------|
| [.ai/startup.md](.ai/startup.md) | Start of each AI session — load, activate, verify |
| [.ai/shutdown.md](.ai/shutdown.md) | End of session — ack, handoff |
| [.ai/capabilities/](.ai/capabilities/README.md) | What agents can do (inbox, send, analyze) |
| [.ai/design/](.ai/design/README.md) | Implementation design (AI-maintained) |
| [.ai/architecture/](.ai/architecture/README.md) | System topology (**human-only — agents read, never edit**) |
| [.ai/integrations/](.ai/integrations/README.md) | Cursor, Claude, Cline, Qoder |
| [.ai/setup/](.ai/setup/README.md) | Full install & daily workflow |
| [.ai/prompts/](.ai/prompts/ready-fa.md) | Copy-paste Persian prompt |

---

## Human operators

| Task | Where |
|------|-------|
| Windows / Linux setup | [.ai/setup/](.ai/setup/README.md) |
| Deploy to VPS | [.ai/architecture/deploy.md](.ai/architecture/deploy.md) |
| Security & constraints | [.ai/architecture/constraints.md](.ai/architecture/constraints.md) |
| Daily Bale workflow | [.ai/setup/daily-workflow.md](.ai/setup/daily-workflow.md) |

## Tests

```bash
source scripts/activate.sh   # or . .\scripts\activate.ps1
pytest -q tests
```

---

## Repo map

```
bale-adapter/
├── .ai/                    # AI agent docs (start here)
├── bale_platform/          # adapter, inbox, outbound, analysis
├── scripts/
│   ├── support_cli.py      # AI-facing CLI
│   ├── install-windows.ps1 # one-liner installer
│   └── login.py            # human-only OTP
├── kb/learn.py             # structured facts (no raw text)
└── pyproject.toml          # uv deps
```
