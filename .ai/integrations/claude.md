# Claude (Desktop / Code)

**Project Instructions:**

```
Read .ai/startup.md and .ai/capabilities/README.md on each session.
Working dir: bale-adapter repo root.
Activate: . .\scripts\activate.ps1 (Windows) or source scripts/activate.sh
CLI: python scripts/support_cli.py
Agent id: set by human (YOUR_NAME)
Never ask for OTP.
```

Ask Claude to summarize JSON from `collect --json` and `analyze --json`.

## MCP (optional)

Claude Desktop can spawn the same MCP server (stdio). Put the token in the client config, not in the repo. Full snippet: [docs/mcp.md](../../docs/mcp.md).

```json
{
  "mcpServers": {
    "bale-adapter": {
      "command": "python",
      "args": ["-m", "bale_platform.mcp_server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/bale-adapter",
        "BALE_MCP_API_BASE_URL": "http://127.0.0.1:8787",
        "BALE_MCP_API_TOKEN": "replace-with-api-token"
      }
    }
  }
}
```
