# Analysis design

Module: `bale_platform/analysis.py`

## Categories (keyword rules)

| Key | Triggers |
|-----|----------|
| `sales` | price, قیمت, register, enroll |
| `education` | level, lesson, teacher, جلسه |
| `technical` | login, minecraft, server, error |
| `gaming` | world, plugin, game |
| `general` | fallback |

## Outputs

**analyze** — counts per category + example snippets + `faq_topic_hints`

**collect** — JSON list of `{chat_id, timestamp, text, category}`

## Future

Replace keyword classifier with LLM batch job; keep CLI shape stable.
