# AI session startup

Run at the **beginning** of every support session.

## 1. Load context (read only)

| Order | Doc |
|-------|-----|
| 1 | `.ai/capabilities/README.md` |
| 2 | `.ai/design/cli-surface.md` |
| 3 | `.ai/design/inbox-store.md` if inbox/ack work |
| 4 | `.ai/architecture/constraints.md` (do not edit) |

## 2. Activate environment

**Windows**

```powershell
cd <repo-root>
. .\scripts\activate.ps1
```

**Linux / macOS**

```bash
cd <repo-root>
source scripts/activate.sh
```

## 3. Verify session (never open the file)

```powershell
python -c "from bale_platform.config import is_configured; exit(0 if is_configured() else 1)"
```

If exit code ≠ 0 → tell the **human** to run bootstrap/login. Do not ask for OTP.

## 4. Confirm agent identity

Ask human once per session if unknown: **support agent id** (e.g. `sara`, `erfan`).
Use the same id in all `--agent` and `ack` commands.

## 5. Sync if runner is offline

```bash
python scripts/support_cli.py sync --dialogs 50 --history 30
```

## 6. Never do at startup

- Read `.session/session.bale`
- Ask for OTP or phone codes
- Edit `.ai/architecture/**`
