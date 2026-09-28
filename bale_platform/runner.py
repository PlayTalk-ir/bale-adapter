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
from bale_platform.api_config import ApiSettings
from bale_platform.config import BaleUserbotConfig
from bale_platform.session_state import session_file_ready

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("bale.runner")


async def main() -> None:
    cfg = BaleUserbotConfig.from_env()
    api_settings = ApiSettings.from_env()

    if not session_file_ready(cfg.session_path):
        if api_settings.enabled:
            logger.warning(
                "No Bale session at %s — HTTP API will start; run scripts/login.py "
                "to authenticate (session can be added without restarting).",
                cfg.session_path,
            )
        else:
            logger.error(
                "No Bale session at %s — run scripts/login.py first to authenticate.",
                cfg.session_path,
            )
            sys.exit(2)
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
