# Staging VPS — team SSH access

Bale adapter deploy stays **root + GitHub Actions** (`VPS_DEPLOY_KEY`). Marketing/content run their own stacks under separate Unix users.

| SSH alias | User | Workdir | Auth |
|-----------|------|---------|------|
| `steach-stage-vps` | `root` | `/opt/bale-adapter` | Operator `~/.ssh/id_rsa` |
| `steach-stage-marketing` | `marketing` | `/srv/marketing` | Dedicated ed25519 key per team/agent |
| `steach-stage-content` | `content` | `/srv/content` | Dedicated ed25519 key per team/agent |

- No shared passwords for SSH; issue keys per person/agent and append to that user’s `authorized_keys`.
- Operator credentials reference: personal agent store `steach-stage-vps-secrets.md` (not in git).
