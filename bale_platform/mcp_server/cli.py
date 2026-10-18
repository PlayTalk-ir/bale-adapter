"""stdio (default) and loopback streamable HTTP entry points."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from bale_platform.mcp_server.client import AdapterApiClient
from bale_platform.mcp_server.config import McpConfigError, McpSettings, ensure_loopback, load_settings
from bale_platform.mcp_server.server import build_server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "MCP server for the PlayTalk Bale adapter. "
            "Talks to the adapter HTTP API with a bearer token. "
            "Does not open the userbot session."
        )
    )
    parser.add_argument(
        "transport",
        nargs="?",
        choices=("stdio", "http"),
        default="stdio",
        help="stdio (default) or http (streamable HTTP on 127.0.0.1)",
    )
    parser.add_argument("--host", default=None, help="HTTP bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="HTTP bind port (default 8790)")
    return parser.parse_args(argv)


def resolve_run(
    argv: list[str] | None = None,
    environ: dict[str, str] | None = None,
) -> tuple[McpSettings, str]:
    """Validate settings. Does not connect or bind."""
    args = parse_args(argv)
    settings = load_settings(environ)
    if args.host:
        settings = replace(settings, http_host=args.host)
    if args.port is not None:
        if args.port < 1 or args.port > 65535:
            raise McpConfigError("--port must be between 1 and 65535.")
        settings = replace(settings, http_port=args.port)
    if args.transport == "http":
        ensure_loopback(settings.http_host, settings.allow_remote_bind)
    return settings, args.transport


def main(argv: list[str] | None = None) -> int:
    try:
        settings, transport = resolve_run(argv)
    except McpConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    client = AdapterApiClient(
        settings.api_base_url,
        settings.api_token,
        timeout=settings.timeout_s,
    )
    server = build_server(client)
    try:
        if transport == "http":
            server.run(
                transport="streamable-http",
                host=settings.http_host,
                port=settings.http_port,
            )
        else:
            server.run(transport="stdio")
    finally:
        client.close()
    return 0
