"""Systemd entry point for the Bale userbot.

Run as:  python -m bale_platform.runner
Invoked by: bale-platform.service ExecStart=
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from bale_platform.adapter import BaleUserbotAdapter
from bale_platform.config import BaleUserbotConfig, is_configured

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("bale.runner")


async def main() -> None:
    if not is_configured():
        logger.error(
            "No Bale session at %s — run scripts/login.py first to authenticate.",
            BaleUserbotConfig.session_path,
        )
        sys.exit(2)

    cfg = BaleUserbotConfig.from_env()
    adapter = BaleUserbotAdapter(cfg)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown(signum, frame):
        logger.info("received signal %s — initiating graceful shutdown", signum)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _shutdown, sig, None)
        except NotImplementedError:
            # Windows / restricted envs — fall back to default handlers
            signal.signal(sig, _shutdown)

    try:
        await adapter.start(stop_event)
    except KeyboardInterrupt:
        logger.info("interrupted")
    except Exception:
        logger.exception("Bale userbot runner crashed")
        raise
    finally:
        await adapter.stop()
        logger.info("runner exit")


if __name__ == "__main__":
    asyncio.run(main())
