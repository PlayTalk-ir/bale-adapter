# Cursor

1. Open repo root in Cursor.
2. Human runs install/bootstrap once (see `.ai/setup/windows.md`).
3. Add rule or paste [../prompts/ready-fa.md](../prompts/ready-fa.md) in Agent chat.
4. Agent reads `.ai/startup.md` at session start.

## Optional rule

Point Cursor at `.ai/startup.md` and forbid editing `.ai/architecture/`.

## MCP (optional)

The adapter also ships an MCP server that calls the HTTP API. It does not replace startup/CLI for ack and FAQ. Config and the tool list: [docs/mcp.md](../../docs/mcp.md).

```json
{
  "mcpServers": {
    "bale-adapter": {
      "command": "python",
      "args": ["-m", "bale_platform.mcp_server"],
      "env": {
        "BALE_MCP_API_BASE_URL": "http://127.0.0.1:8787",
        "BALE_MCP_API_TOKEN": "replace-with-api-token"
      }
    }
  }
}
```

## Sample requests

- «پیام‌های خوانده‌نشده من را نشان بده»
- «نگرانی‌های مشتریان را تحلیل کن»
- «برای FAQ استخراج کن»
