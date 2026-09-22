# Privacy design

## Never persist via AI tools

- OTP codes
- Raw session bytes (`.session/session.bale`)

## Two-tier storage

| Tier | File | Raw text? |
|------|------|-----------|
| KB facts | `kb/learned_facts.mdl` | No — regex facts only, PII blocked |
| Inbox | `data/support_inbox.sqlite` | Yes — needed for FAQ/unread |

## PII filter

`kb/learn.py` blocks national-id-like patterns before fact extraction.

## Agent rule

Do not copy customer message bodies into git-tracked markdown or commits.
