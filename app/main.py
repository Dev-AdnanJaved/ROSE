import asyncio
from app.core.logger import logger
from app.exchange import symbols as symbol_cache
from app.market.marketcap_updater import fetch_marketcaps, start_marketcap_updater
from app.gateway.telegram_gateway import start_telegram
from app.strategy.signal_router import start_router


async def _prewarm():
    logger.info("Pre-warming caches...")
    try:
        await symbol_cache.warmup()
    except Exception as e:
        logger.exception(f"FATAL: symbol cache warmup failed: {e}")
        raise SystemExit(1)
    try:
        await fetch_marketcaps()
    except Exception as e:
        logger.warning(f"Market cap prefetch failed (will retry on schedule): {e}")
    logger.info("Pre-warm complete")


async def start():
    await _prewarm()
    await asyncio.gather(
        start_telegram(),
        start_router(),
        start_marketcap_updater(),
    )
