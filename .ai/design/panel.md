# Admin panel design

Modules: `bale_platform/panel.py`, `panel_ui.py`, `panel_auth.py`,
`paths.py`, entry `scripts/panel.py`, unit `systemd/bale-panel.service`.

## Why

Support staff should not have to type terminal commands: open the panel, type a
name in one box, the message in another, send. Everything the CLI can show
(contact book, inbox, messages, analysis, KB facts, log) is rendered as pages.

**No new dependency** — the panel is built on `aiohttp.web`, which is already a
project dependency (`requirements.txt`). HTML is rendered with plain string
templates in `panel_ui.py` (no Jinja2).

## Pages

| Route | Content |
|-------|---------|
| `/` | stats cards + send form + latest messages + analysis |
| `/contacts` | book table, search, manual add/remove, refresh-from-Bale job |
| `/inbox` | per-chat and per-agent unread (offline) + sync/live-unread jobs |
| `/messages` | stored messages with chat/direction/limit filters |
| `/analysis` | concern buckets + FAQ hints + sync job |
| `/system` | paths, KB facts tail, runner log tail |
| `/job`, `/api/job` | one background job at a time, log polled every 2s |
| `/login`, `/logout` | operator token → signed cookie |

## Security

* one operator token (`BALE_PANEL_TOKEN`, or a random one printed at startup);
  `hmac.compare_digest` + 1s sleep on failure;
* cookie = `<expiry>.<hmac>` signed with the token (`panel_auth.make_session`),
  `HttpOnly`, `SameSite=Strict`, 7-day TTL;
* every state-changing POST carries `_csrf` derived from the cookie;
* default bind `127.0.0.1:8090` — expose through an SSH tunnel, never public;
* all customer text is rendered via `panel_ui.esc`; pre-rendered markup must be
  wrapped in `panel_ui.Raw` (XSS guard, covered by tests).

## Jobs

Network actions (send / refresh / sync / live unread) run as one background
`asyncio` task writing to a `Job` log; the browser polls `/job` → `/api/job`.
Only one job at a time (`start_job` returns `None` while busy → `?busy=1`).
A preview (`dry-run`) job stores the payload in `job.confirm` so the page can
offer a **تأیید و ارسال** button for the real send.

## Send flow

`POST /send` → `parse_inline` (names/phones/ids, one per line) → `_make_send_runner`
→ `send_to_targets(index=book.to_index())`. Resolution uses the local contact
book, so names cost no API calls; ambiguous names FAIL with candidate chat ids.
