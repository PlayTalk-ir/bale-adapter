"""Environment for the MCP process. The API token stays out of the repo."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_API_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8790
DEFAULT_TIMEOUT_S = 30.0

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class McpConfigError(ValueError):
    """The MCP process cannot start with the current environment."""


@dataclass(frozen=True)
class McpSettings:
    api_base_url: str
    api_token: str
    http_host: str = DEFAULT_HTTP_HOST
    http_port: int = DEFAULT_HTTP_PORT
    timeout_s: float = DEFAULT_TIMEOUT_S
    allow_remote_bind: bool = False


def _flag(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def load_settings(environ: dict[str, str] | None = None) -> McpSettings:
    """Read MCP settings. ``BALE_MCP_API_TOKEN`` is required."""
    env = os.environ if environ is None else environ
    base = (env.get("BALE_MCP_API_BASE_URL") or DEFAULT_API_BASE_URL).strip().rstrip("/")
    token = (env.get("BALE_MCP_API_TOKEN") or "").strip()
    host = (env.get("BALE_MCP_HTTP_HOST") or DEFAULT_HTTP_HOST).strip() or DEFAULT_HTTP_HOST
    port_raw = (env.get("BALE_MCP_HTTP_PORT") or str(DEFAULT_HTTP_PORT)).strip()
    timeout_raw = (env.get("BALE_MCP_TIMEOUT_S") or str(DEFAULT_TIMEOUT_S)).strip()

    if not token:
        raise McpConfigError(
            "BALE_MCP_API_TOKEN is required. Issue a bearer token in the admin panel "
            "(توکن API) or via BALE_ADAPTER_API_TOKENS, then put that plaintext only "
            "in the MCP process environment."
        )
    if any(ch.isspace() for ch in token):
        raise McpConfigError("BALE_MCP_API_TOKEN must be a single token with no whitespace.")

    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise McpConfigError(
            "BALE_MCP_API_BASE_URL must be an http(s) origin, for example http://127.0.0.1:8787"
        )
    if parsed.username or parsed.password:
        raise McpConfigError("Put the API token in BALE_MCP_API_TOKEN, not in the base URL.")
    if parsed.query or parsed.fragment:
        raise McpConfigError("BALE_MCP_API_BASE_URL must be an origin without a query or fragment.")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise McpConfigError("BALE_MCP_HTTP_PORT must be an integer.") from exc
    if port < 1 or port > 65535:
        raise McpConfigError("BALE_MCP_HTTP_PORT must be between 1 and 65535.")

    try:
        timeout_s = float(timeout_raw)
    except ValueError as exc:
        raise McpConfigError("BALE_MCP_TIMEOUT_S must be a number of seconds.") from exc
    if timeout_s <= 0:
        raise McpConfigError("BALE_MCP_TIMEOUT_S must be greater than 0.")

    return McpSettings(
        api_base_url=base,
        api_token=token,
        http_host=host,
        http_port=port,
        timeout_s=timeout_s,
        allow_remote_bind=_flag(env.get("BALE_MCP_HTTP_ALLOW_REMOTE")),
    )


def ensure_loopback(host: str, allow_remote: bool) -> None:
    """Streamable HTTP listens on loopback unless the operator opts out.

    The MCP process holds an API token and does not authenticate its own
    callers. Binding a public interface would expose the shared userbot.
    """
    if host in _LOOPBACK_HOSTS:
        return
    if allow_remote:
        return
    raise McpConfigError(
        f"Refusing to bind MCP HTTP to {host!r}. "
        "The default is 127.0.0.1 because this process has no auth of its own. "
        "Set BALE_MCP_HTTP_ALLOW_REMOTE=true only on a private network you control."
    )
