"""Shared aiobale client lifecycle for CLI tools and the long-running runner."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Any

from bale_platform.config import BaleUserbotConfig


@asynccontextmanager
async def bale_client(cfg: BaleUserbotConfig | None = None) -> AsyncIterator[Any]:
    """Connect with the saved session; disconnect on exit."""
    cfg = cfg or BaleUserbotConfig.from_env()
    if not cfg.session_path.exists():
        raise RuntimeError(
            f"session file not found at {cfg.session_path} — run scripts/login.py first."
        )

    from aiobale import Client, Dispatcher  # type: ignore[import-not-found]

    dp = Dispatcher()
    client = Client(dispatcher=dp, session_file=str(cfg.session_path))
    await client.start(run_in_background=True)
    try:
        yield client
    finally:
        await client.stop()
