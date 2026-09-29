# Contacts & target resolution

Modules: `bale_platform/contacts.py`, `bale_platform/targets.py`,
`bale_platform/outbound.py`

## Why

Support staff know customers by the name saved in Bale ("نفس پیروز"), not by
chat id. `send` therefore resolves three target kinds: **saved name**, phone, chat id.

## Contact index

`build_contact_index(client, include_dialogs=True, dialog_limit=200, chunk_size=50)`

1. **Address book** — `client.load_contacts()` → `load_users(peers)` (batched,
   `chunk_size` per call). Per-peer `load_user` is the fallback when a batch fails.
   Observed on the PlayTalk account: `load_contacts()` returns **0 rows**, so the
   resolvable names come from dialogs (`local_name` is still the name we saved).
2. **Dialogs** (optional) — private peers from `load_dialogs(limit=…)`.

Each entry keeps `local_name` (the name we saved), `profile_name`, `username`.
Display name = `local_name or profile_name or username or chat_id`.

The live index is **transient** (used by `contacts --refresh`); `send` resolves
against the persistent book below.

## Persistent contact book (`contact_store.py`)

File: `data/contacts.sqlite` (override `BALE_CONTACTS_PATH`). Table `contacts`:
`chat_id` (PK), `name`, `local_name`, `profile_name`, `username`, `source`,
`manual`, `created_at`, `updated_at`.

| Command | Effect |
|---------|--------|
| `contacts` | list the book (**no session needed**) |
| `contacts --search NAME` | fuzzy filter |
| `contacts --refresh` | pour Bale's dialogs (+ address book) into the book |
| `contacts --add "NAME=CHAT_ID"` | manual entry (or `=PHONE`, needs a session) |
| `contacts --remove CHAT_ID` | delete an entry |
| `contacts --prune` | with `--refresh`: drop non-manual rows Bale no longer reports |
| `contacts --json` | machine-readable dump |

Refresh policy (`refresh_book` → `ContactBook.upsert_bale`):

* new rows are **added**; existing non-manual rows are **updated**;
* a row added by hand is **kept** — its `name` and `manual=1` survive, only the
  Bale fields (`local_name` / `profile_name` / `username`) are refreshed;
* `prune` never deletes manual rows.

`send` builds its `ContactIndex` from the book (`ContactBook.to_index()`), so a
name send costs **zero** extra API calls. Unknown names fail with a hint to run
`contacts --refresh` or `contacts --add`.

## Name folding (`normalize_name`)

Arabic/Persian variants (`ي`→`ی`, `ك`→`ک`, `ة`→`ه`, `آ`→`ا`, …), ZWNJ/bidi
marks, Persian digits, emoji and decoration are folded away. Every contact gets
two keys per name variant — spaced and compact — so "امیر حافظ سفیدبری"
matches the saved "امیرحافظ سفیدبری".

## Match order (never guesses)

1. exact variant match (saved name, profile name, username)
2. prefix match
3. substring match

`NameNotFound` / `NameNotUnique` are returned per target, the latter listing
candidate chat ids — the adapter never picks one of several matches.

## Target parsing (`targets.py`)

| Source | Handling |
|--------|----------|
| `--to` | split on `,` `;` `،` tab and newlines; bullets/numbering/quotes stripped |
| `.txt` | one target per line, same cleaning |
| `.csv` / `.tsv` | delimiter auto-detected (`,` `;` tab); utf-8 / utf-16 / cp1256 |
| `.xlsx` / `.xlsm` | stdlib reader (zipfile + ElementTree); shared + inline strings, numeric cells |

One cell per row is used (`--column`, else first non-empty) so a `name,phone`
row cannot be sent twice. Title rows are detected automatically.

## Classification (`classify_target`)

| Pattern | Kind |
|---------|------|
| starts with `+` | phone |
| 11 digits starting `0` | phone |
| 12 digits starting `98` | phone |
| other ≤ 12 digits | chat id |
| anything else | name |

This also fixed a real bug: `09924466793` used to be read as chat id `9924466793`.
