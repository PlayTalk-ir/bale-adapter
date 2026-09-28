"""Session file presence check (config-aware)."""

from __future__ import annotations

from pathlib import Path


def session_file_ready(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0
