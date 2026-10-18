"""MCP server that talks to the Bale adapter only through its HTTP API.

The official Python MCP SDK renamed ``FastMCP`` to ``MCPServer`` in mcp 2.x
(``mcp.server.mcpserver``). This package uses that class. It never opens the
userbot session file or the inbox/outbox databases.
"""

from bale_platform.mcp_server.server import INSTRUCTIONS, build_server

__all__ = ["INSTRUCTIONS", "build_server"]
