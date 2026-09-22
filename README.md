# bale-adapter

---

## راهنمای فارسی — نصب و استفاده با دستیار هوش مصنوعی

این ابزار به **دستیار AI** (Cursor، Claude، Cline، Qoder و …) اجازه می‌دهد با
**اکانت مشترک بله پلی‌تاک** کار کند: پیام بفرستد، پیام‌های مشتری را بخواند،
موضوعات FAQ را استخراج کند، و بفهمد هر پشتیبان چه چیز «خوانده‌نشده» دارد.

> **مهم:** همه پشتیبان‌ها (فروش، آموزشی، فنی، مدرس) روی **یک اکانت** کار
> می‌کنند. OTP فقط **یک بار** در ترمینال وارد می‌شود — هرگز OTP را در چت AI
> نپیستید.

### پیش‌نیاز

- **Git** و **اینترنت** (Python و uv خودکار نصب می‌شوند)
- شماره **اکانت شرکت** پلی‌تاک که OTP بله را دریافت کند

---

### نصب — ویندوز (یک خط)

PowerShell را باز کنید و **فقط این یک خط** را paste کنید (Git، clone، uv، Python،
login — همه خودکار):

```powershell
irm https://raw.githubusercontent.com/PlayTalk-ir/bale-adapter/master/scripts/install-windows.ps1 | iex
```

### نصب — ویندوز (دستی)

```powershell
git clone https://github.com/PlayTalk-ir/bale-adapter.git
cd bale-adapter
. .\scripts\bootstrap.ps1
```

این دستور به ترتیب:
1. **uv** و **Python 3.12** را نصب می‌کند
2. وابستگی‌ها را با `uv sync` نصب می‌کند
3. محیط را فعال می‌کند
4. اگر session ندارید، **لاگین تعاملی** را باز می‌کند (شماره + OTP)

| ورودی شما | تبدیل می‌شود به |
|-----------|----------------|
| `09924466793` | `989924466793` |
| `+989924466793` | `989924466793` |

**نکته:** حتماً با **نقطه** اجرا کنید: `. .\scripts\bootstrap.ps1`  
(بدون نقطه، venv در همان shell فعال نمی‌ماند.)

اگر Policy اجرا را block کرد:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
powershell -NoExit -ExecutionPolicy Bypass -Command ". .\scripts\bootstrap.ps1"
```

**جلسات بعدی** (بدون نصب مجدد):

```powershell
cd مسیر\bale-adapter
. .\scripts\activate.ps1
```

---

### نصب — لینوکس / macOS

```bash
git clone https://github.com/PlayTalk-ir/bale-adapter.git
cd bale-adapter
chmod +x scripts/bootstrap-local.sh scripts/ensure-uv.sh
./scripts/bootstrap-local.sh
```

جلسات بعدی: `source scripts/activate.sh`

---

### کارهای روزانه

**۱. شنود پیام‌های جدید** (یک ترمینال باز بماند):

```powershell
python -m bale_platform.runner
```

**۲. همگام‌سازی inbox** (اگر runner خاموش است):

```powershell
python scripts\support_cli.py sync --dialogs 50 --history 30
```

**۳. بعد از پاسخ دادن** — علامت «رسیدگی شد» برای خودتان:

```powershell
python scripts\support_cli.py ack --agent YOUR_NAME --chat CHAT_ID --message-id MSG_ID
```

`YOUR_NAME` همان نام کوتاه شماست (مثلاً `sara`، `erfan`) — در همه دستورات
یکسان بمانید.

---

### دستورات اصلی برای AI

| کار | دستور |
|-----|--------|
| پیام به چند نفر | `python scripts/support_cli.py send --to 09xx,09yy --text "متن"` |
| پیام‌های خوانده‌نشده (کل اکانت) | `python scripts/support_cli.py inbox --unread` |
| پیام‌های من (پس از ack) | `python scripts/support_cli.py inbox --agent YOUR_NAME` |
| جمع‌آوری برای FAQ | `python scripts/support_cli.py collect --json --limit 50` |
| تحلیل نگرانی مشتریان | `python scripts/support_cli.py analyze` |
| تست ارسال بدون فرستادن | `... send --to 09xx --text "..." --dry-run` |

---

### اتصال به دستیار AI

ایده مشترک همه ابزارها: **AI باید دستورات `support_cli.py` را در ترمینال
پروژه اجرا کند** — نه اینکه OTP یا session را ببیند.

#### Cursor

1. پروژه `bale-adapter` را در Cursor باز کنید.
2. یک بار bootstrap + login را **خودتان** در ترمینال انجام دهید.
3. در چت Agent بنویسید:

```
تو دستیار پشتیبانی بله پلی‌تاک هستی. قبل از هر کار:
. .\scripts\activate.ps1
سپس از scripts/support_cli.py استفاده کن.
agent من: sara
```

4. (اختیاری) Rule در `.cursor/rules/` بسازید تا Agent همیشه `activate` کند و
   `--agent sara` را بداند.

**نمونه درخواست‌ها:**
- «پیام‌های خوانده‌نشده من را نشان بده»
- «نگرانی‌های این هفته مشتریان را تحلیل کن»
- «۵۰ پیام آخر را برای FAQ استخراج کن»
- «به این شماره‌ها پیام بفرست: …»

#### Claude (Desktop / Code)

1. پروژه را clone و bootstrap کنید.
2. در **Project Instructions** یا ابتدای مکالمه:

```
Working directory: bale-adapter
Run shell commands only after: . .\scripts\activate.ps1  (Windows)
Use: python scripts/support_cli.py …
My agent id: sara
Never ask for OTP — session already on disk.
```

3. از Claude بخواهید خروجی JSON دستورات `collect` و `analyze` را خلاصه کند.

#### Cline (VS Code)

1. Extension Cline را نصب کنید؛ workspace را `bale-adapter` قرار دهید.
2. در Cline settings → **Terminal Integration** را فعال کنید.
3. System prompt:

```
You can run bale-adapter CLI in the integrated terminal.
Always activate first: . .\scripts\activate.ps1
Support agent name: sara
Commands live in scripts/support_cli.py
```

4. Cline می‌تواند `run_terminal_cmd` بزند — همان دستورات جدول بالا.

#### Qoder

1. Repository را در Qoder باز کنید.
2. در Agent / Chat settings، **Allow terminal** را روشن کنید.
3. Context یا Custom Instructions:

```
Repo: bale-adapter (PlayTalk Bale support)
Before CLI: source scripts/activate.ps1 OR . .\scripts\activate.ps1
CLI entrypoint: python scripts/support_cli.py
My --agent id: sara
```

4. مثل Cursor از Agent بخواهید inbox، analyze، send را اجرا کند.

---

### پرامپت آماده (کپی در هر AI)

```
شما دستیار پشتیبانی بله پلی‌تاک هستید.

قوانین:
- OTP و session را هرگز نپرسید.
- قبل از هر دستور: محیط را فعال کنید (activate.ps1 / activate.sh).
- شناسه agent من: YOUR_NAME
- فقط از scripts/support_cli.py استفاده کنید.
- قبل از send واقعی، یک بار --dry-run پیشنهاد دهید.
- بعد از پاسخ کامل به مشتری، ack بزنید.

دستورات:
  sync | inbox [--unread | --agent NAME] | collect --json | analyze | send | ack
```

---

### دسته‌بندی خودکار پیام‌ها

| دسته | مثال |
|------|------|
| `sales` | قیمت، ثبت‌نام |
| `education` | سطح، جلسه، مدرس |
| `technical` | ورود، سرور، ماین‌کرافت |
| `gaming` | ورلد، پلاگین، بازی |
| `general` | سایر |

---

### English documentation

Technical details, architecture, deploy, and security notes continue below.

---

Bale userbot adapter (Shape C) for **PlayTalk**'s shared company Bale account.
Support staff (sales, education, technical, teachers) currently all use one
login manually. This service lets **AI agents** interact with that same account
safely: send broadcasts, read the inbox, mine FAQ topics, and track what each
agent still needs to handle.

Runs as a systemd service on the same VPS as `nexa-backend`.

## Support agent capabilities

| Goal | CLI command | Notes |
|------|-------------|-------|
| Send a message to a list of people | `support_cli.py send --to 09…,09… --text "…"` | Resolves phones → private chats |
| Collect customer messages for FAQ | `support_cli.py collect --json` | Exports categorized incoming text |
| Analyze current customer concerns | `support_cli.py analyze` | Buckets: sales / education / technical / gaming |
| Check unread for a specific agent | `support_cli.py inbox --agent sara` | Uses per-agent acks (see below) |
| Account-wide unread (shared login) | `support_cli.py inbox --unread` | Bale's native unread on the company account |

```bash
# After login + runner (or manual sync):
python scripts/support_cli.py sync --dialogs 50 --history 30
python scripts/support_cli.py inbox --agent sara
python scripts/support_cli.py analyze --json
python scripts/support_cli.py send --to 09924466793 --text "سلام از پلی‌تاک"
python scripts/support_cli.py ack --agent sara --chat 123456 --message-id 999
```

### Shared account → per-agent unread

Bale only knows **one** unread counter for the company login. When any support
person reads a chat in the Bale app, it clears for everyone.

This adapter adds a local inbox store (`data/support_inbox.sqlite`) that:

1. Records incoming/outgoing messages (while the runner is up, or via `sync`)
2. Tracks `agent_acks` — which message each support agent last handled
3. Answers **"what is unread for Sara?"** = customer messages after Sara's last ack

Agents should run `ack` when they finish a conversation (or teach their AI agent
to call it). Until then, use `inbox --unread` for the shared account view.

### Message categories (for concern analysis)

| Category | Typical topics |
|----------|----------------|
| `sales` | pricing, enrollment, registration |
| `education` | levels, lessons, teachers, sessions |
| `technical` | login, Minecraft server, install errors |
| `gaming` | worlds, plugins, in-game issues |
| `general` | everything else |

Keyword rules live in `bale_platform/analysis.py` — extend for PlayTalk-specific
phrases or swap in an LLM later.

### Privacy split

- **`kb/learned_facts.mdl`** — structured facts only (no raw message text)
- **`data/support_inbox.sqlite`** — short-term message cache for support tools
  (needed for FAQ mining and per-agent unread). Keep on the VPS; do not commit.

## Architecture

```
VPS (130.185.76.124)
└── /opt/bale-adapter/
    ├── .session/session.bale         # aiobale session (opaque protobuf, 0600)
    ├── data/support_inbox.sqlite     # per-agent inbox + message cache
    ├── venv/                          # Python venv with aiobale
    ├── bale_platform/                 # adapter code
    │   ├── adapter.py                 # long-running listener + store
    │   ├── inbox.py / outbound.py     # read + send helpers
    │   ├── analysis.py                # concern + FAQ mining
    │   ├── store.py                   # SQLite inbox
    │   ├── config.py                  # BaleUserbotConfig
    │   └── runner.py                  # systemd entry point
    ├── kb/learn.py                    # observe-extract (PII-aware facts)
    ├── scripts/support_cli.py         # support-agent CLI (for AI tools)
    ├── systemd/bale-platform.service  # systemd unit
    ├── scripts/bootstrap.sh           # VPS systemd bootstrap (/opt/bale-adapter)
    ├── scripts/bootstrap-local.sh     # local Linux/macOS bootstrap + login
    ├── scripts/bootstrap.ps1          # local Windows bootstrap + login
    ├── scripts/activate.sh / activate.ps1
    ├── scripts/login.py               # one-time interactive login
    └── .env                           # BALE_SESSION_PATH, BALE_STORE_PATH, ...
```

## Why aiobale, not the Bale Bot API

PlayTalk needs the userbot to read **all** customer messages in their company
account, including ones not addressed to a bot. The official `dev.bale.ai`
Bot API only sees messages where the bot is added/mentioned. `aiobale`
(reverse-engineered, GitHub-only — PyPI version is an empty shell) lets us
log into the company account as that user.

> ⚠️ aiobale is unofficial. Excessive POST gRPC calls may trigger Bale rate
> limits. Outbound sends are explicit via `support_cli.py send` — the long-running
> runner does not auto-reply unless you call the send tool.

## Local development

### Prerequisites

- **Git**
- **Internet** (bootstrap installs [uv](https://docs.astral.sh/uv/) + Python 3.12 automatically)
- A Bale company-account phone that can receive OTP

No manual Python install needed — bootstrap runs `uv python install 3.12` and
`uv sync` from `pyproject.toml`.

---

### Linux / macOS

```bash
git clone https://github.com/PlayTalk-ir/bale-adapter.git
cd bale-adapter
chmod +x scripts/bootstrap-local.sh scripts/activate.sh
./scripts/bootstrap-local.sh    # venv + deps + activate + login (if no session)

pytest -q tests
python -m bale_platform.runner  # listen (Ctrl+C to stop)

python scripts/support_cli.py sync
python scripts/support_cli.py inbox --unread
```

`bootstrap-local.sh` installs **uv** (if missing), **Python 3.12**, project deps
via `uv sync`, activates the shell, and starts interactive login when there is
no session. Re-run safely with `--skip-login` to refresh deps only.

Later terminal sessions:

```bash
source scripts/activate.sh
```

---

### Windows

Open **PowerShell** (or Windows Terminal). Run from the repo root.

#### 1. Clone and bootstrap (venv + activate + login)

**Dot-source** so the venv stays active in your shell:

**One-liner (Git + clone + bootstrap):**

```powershell
irm https://raw.githubusercontent.com/PlayTalk-ir/bale-adapter/master/scripts/install-windows.ps1 | iex
```

**Manual:**

```powershell
git clone https://github.com/PlayTalk-ir/bale-adapter.git
cd bale-adapter
. .\scripts\bootstrap.ps1
```

`bootstrap.ps1` installs **uv** (if missing), **Python 3.12**, syncs deps into
`venv/` via `uv sync`, runs `activate.ps1`, and starts interactive login when
there is no session.

If execution policy blocks scripts:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# or one-shot dot-source:
powershell -NoExit -ExecutionPolicy Bypass -Command ". .\scripts\bootstrap.ps1"
```

Re-run without login (deps refresh only):

```powershell
. .\scripts\bootstrap.ps1 -SkipLogin
```

#### 2. Later sessions — activate only

```powershell
cd j:\dev\minecraft\bale-adapter
. .\scripts\activate.ps1
```

> **Windows notes**
> - Use `. .\scripts\...` (dot-source), not `.\scripts\...` alone, to keep the venv active.
> - OTP login **must** be interactive — type phone and OTP yourself (no piping).
> - `PYTHONIOENCODING=utf-8` is set automatically by `activate.ps1`.

#### 3. Tests

```powershell
pytest -q tests
# or explicitly:
.\venv\Scripts\pytest.exe -q tests
```

#### 4. Login (if bootstrap skipped it)

Bootstrap runs this automatically when there is no session. To log in again:

```powershell
. .\scripts\activate.ps1
python scripts\login.py
# phone: 09924466793   (or +989924466793)
# OTP:   type the code Bale sends (input is hidden)
```

| You type | Normalized to |
|----------|---------------|
| `09924466793` | `989924466793` |
| `989924466793` | `989924466793` |
| `+989924466793` | `989924466793` |

#### 5. Run the listener

```powershell
python -m bale_platform.runner
```

Press `Ctrl+C` to stop. Structured facts go to `kb\learned_facts.mdl`; messages
also land in `data\support_inbox.sqlite`.

#### 6. Support agent CLI

```powershell
python scripts\support_cli.py sync --dialogs 50 --history 30
python scripts\support_cli.py inbox --unread
python scripts\support_cli.py inbox --agent sara
python scripts\support_cli.py collect --json --limit 50
python scripts\support_cli.py analyze
python scripts\support_cli.py send --to 09924466793 --text "سلام" --dry-run
python scripts\support_cli.py ack --agent sara --chat 123456 --message-id 999
```

#### 7. Copy session to VPS (optional)

From PowerShell with OpenSSH client (`scp` ships on Windows 10+):

```powershell
scp .session\session.bale root@130.185.76.124:/opt/bale-adapter/.session/session.bale
ssh root@130.185.76.124 "chmod 600 /opt/bale-adapter/.session/session.bale; systemctl restart bale-platform"
```

---

### Env vars (all platforms)

| Variable | Default | Purpose |
|----------|---------|---------|
| `BALE_SESSION_PATH` | `/opt/bale-adapter/.session/session.bale` | aiobale session file |
| `BALE_KB_DIR` | `/opt/bale-adapter/kb` | KB output directory |
| `BALE_LOG_FILE` | `/opt/bale-adapter/logs/userbot.log` | Log file path |
| `BALE_STORE_PATH` | `data/support_inbox.sqlite` | SQLite inbox for per-agent unread |
| `BALE_OBSERVE_ONLY` | `true` | Runner never auto-replies |
| `BALE_ALLOWED_CHATS` | *(empty = all)* | Comma-separated chat IDs to watch |
| `PYTHONIOENCODING` | — | Set to `utf-8` on Windows before login |

### Test fact extraction standalone

```bash
python kb/learn.py "قیمت دوره ۲ میلیون تومان"
python kb/learn.py "child age: 9"
```

```powershell
python kb\learn.py "قیمت دوره ۲ میلیون تومان"
python kb\learn.py "child age: 9"
```

## Deploy

```bash
git push origin master
# → GitHub Actions: install deps, run tests, ssh into VPS, git pull + restart
```

If the service exits with `No Bale session at ...`, the session file is
missing. Run `scripts/login.py` on the VPS console — the OTP is typed into
that terminal and never leaves the VPS:

```bash
ssh root@130.185.76.124
cd /opt/bale-adapter
source venv/bin/activate
python scripts/login.py
# → enter phone → Bale sends OTP → enter OTP → session written
systemctl restart bale-platform.service
```

After a successful local login you can copy the session to the VPS instead
of re-authenticating (same company account):

```bash
scp .session/session.bale root@130.185.76.124:/opt/bale-adapter/.session/session.bale
ssh root@130.185.76.124 'chmod 600 /opt/bale-adapter/.session/session.bale && systemctl restart bale-platform'
```

## Security

- Session file is `0700` dir + `0600` file
- OTP is read via `getpass`, never logged, never sent to Hermes
- The userbot observes all chats the company account is part of — PlayTalk
  consented to this; the userbot is intended for a corporate account, not
  personal use
- `kb/learned_facts.mdl` stores structured facts only (PII-filtered)
- `data/support_inbox.sqlite` caches messages for support tools — keep local/VPS only

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q tests
```

Tests use `tests/_aiobale_stub.py` to avoid pulling in aiobale on CI.
