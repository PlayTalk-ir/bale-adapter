# /brag plan — bale-adapter

Run via `/brag` → `/brag-slim` (Opus 5.5). Tone `default`, landscape 1920×1080, 30fps, 21s.

## Rubric

- **What is it?** A tool that connects PlayTalk's shared Bale support account to AI assistants (Cursor, Claude, Cline, Qoder).
- **Who is it for?** PlayTalk support staff. They get the Bale inbox, replies and FAQ mining inside the AI editor they already use.
- **What sets it apart?** One shared login for the whole team, per-agent unread tracking, and hard guardrails: `--dry-run` first, and a human approves every real send.
- **Most impressive claim:** "Support staff can send messages, read inbox, mine FAQ topics, and track per-agent unread." (README)
- **Visual hook:** Persian customer messages stacking up with an unread counter ticking up, then the answer: the inbox, handled from Cursor.
- **Real UI / flow:** `support_cli.py inbox --unread` → `send … --dry-run` → the admin panel (`panel_ui.py`, Vazirmatn, RTL, `#2456d6`) where a human presses «اجرا».
- **Tone:** default. Punchy and clean, with a small wink on "a human still presses send".
- **Share caption:** Our Bale support inbox now answers from Cursor. The AI reads, drafts and dry-runs, and a human still presses send.

## Angle

Your Bale support inbox, answered from your AI editor, and a human still presses send.

## Visual identity

The panel's own palette: ink `#1d2433`, muted `#6b7280`, line `#e5e7eb`, bg `#f6f7fb`, accent `#2456d6`, ok `#0a7d33`; dark log `#0f1420` / `#d7e0ff`. Font Vazirmatn (Persian and Latin), with a monospace font for the CLI. All names, chat ids and messages on screen are fake demo data.

## Storyboard (21.0s)

| # | Time | Scene | On screen | Motion / sound |
|---|------|-------|-----------|----------------|
| 1 | 0.0–3.2 | Hook | Fake Persian customer bubbles pop in on the right. A red unread badge counts 1→12. Headline: **"Bale inbox piling up?"** | Bubbles spring in, one soft blip each (in key). Kick enters. |
| 2 | 3.2–6.8 | Reveal | Wordmark **bale-adapter**. Line: "Your shared Bale account, inside your AI editor." Chips: Cursor · Claude · Cline · Qoder. | Bubbles sweep out, then the wordmark scales in. Chips pop one by one. Riser into the downbeat. |
| 3 | 6.8–10.6 | Highlight 1 | Terminal (panel `.log` style). The command types `python scripts/support_cli.py inbox --unread`, then real-format `chat=… unread=…` lines print. Caption: **"Your AI reads the inbox."** | Typing ticks under the music. Lines stagger in. |
| 4 | 10.6–14.6 | Highlight 2 | The same terminal types `send --to "سارا م." --text "…" --dry-run`, then `[OK] target=… → سارا م. chat_id=… ` and `# 1/1 ok (dry-run — nothing sent)`. Caption: **"Drafts the reply. Dry-run first."** | Green OK flash with a soft chime. |
| 5 | 14.6–18.2 | Highlight 3 | The real admin panel (header «پنل ادمین بله پلی‌تاک», nav, send card, textareas prefilled). A cursor moves to «اجرا» and clicks, and a `.notice` appears: «ارسال شد — ۱/۱ OK». Caption: **"A human still presses send."** | Cursor glide, click sfx, notice slides down. |
| 6 | 18.2–21.0 | Outro | **bale-adapter**. Line: "You approve. It sends." Small text: "PlayTalk · Cursor · Claude · Cline · Qoder". | Hold. Music resolves on the tonic. |

Durations: 3.2 + 3.6 + 3.8 + 4.0 + 3.6 + 2.8 = 21.0s.

## Sound

About 112 BPM in A minor, synthesized: soft kick, filtered pad chords (Am–F–C–G), and a pluck arpeggio. The sound effects (blips, ticks, chime, click) are pitched to A minor and kept 10–14 dB under the music. The track fades out at the end.
