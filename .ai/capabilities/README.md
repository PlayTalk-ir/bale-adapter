# Capabilities

What support AI agents can do via terminal (after activate + session exists).

| Capability | Doc |
|------------|-----|
| Read inbox / unread | [inbox.md](inbox.md) |
| Send messages | [outbound.md](outbound.md) |
| FAQ mining | [analysis.md](analysis.md) |
| Live listen | [runner.md](runner.md) |

## Hard limits

- No OTP / login on behalf of human
- No auto-send without human approval (use `--dry-run` first)
- No edits to `.ai/architecture/`
