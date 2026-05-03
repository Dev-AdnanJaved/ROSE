import asyncio
from app.core.logger import logger
from app.core.config import Config
from app.exchange import symbols as symbol_cache
from app.exchange.account import (
    detect_position_mode, get_open_position_symbols, has_open_positions,
    get_available_usdt,
)
from app.exchange.binance_client import close_client
from app.market.marketcap_updater import fetch_marketcaps, start_marketcap_updater
from app.gateway.telegram_gateway import start_telegram
from app.strategy.signal_router import start_router
from app.strategy import trade_history
from app.telegram.command_bot import start_command_bot


async def _watch_preexisting_positions():
    from app.strategy import signal_router
    while True:
        await asyncio.sleep(15)
        if signal_router._current_trade != "PRE_EXISTING_POSITION":
            return
        try:
            if not await has_open_positions():
                async with signal_router._busy_lock:
                    signal_router._busy = False
                    signal_router._current_trade = None
                logger.info("Pre-existing positions closed — bot is now ready to trade")
                return
        except Exception as e:
            logger.warning(f"pre-existing position check error: {e}")


async def _prewarm():
    logger.info("Pre-warming caches...")
    try:
        await symbol_cache.warmup()
    except Exception as e:
        logger.exception(f"FATAL: symbol cache warmup failed: {e}")
        raise SystemExit(1)

    await detect_position_mode()

    trade_history.load()
    try:
        bal = await get_available_usdt(force_refresh=True)
        if bal > 0:
            await trade_history.set_initial_balance(bal)
    except Exception as e:
        logger.warning(f"initial balance snapshot failed: {e}")

    open_syms = await get_open_position_symbols()
    if open_syms:
        logger.warning(
            f"WARNING: {len(open_syms)} open futures position(s) detected at startup: "
            f"{open_syms}. Bot will refuse to open new trades until these are closed."
        )
        from app.strategy import signal_router
        signal_router._busy = True
        signal_router._current_trade = "PRE_EXISTING_POSITION"
        asyncio.create_task(_watch_preexisting_positions())

    try:
        await fetch_marketcaps()
    except Exception as e:
        logger.warning(f"Market cap prefetch failed (will retry on schedule): {e}")
    logger.info("Pre-warm complete")


async def start():
    try:
        await _prewarm()
        tasks = [
            start_telegram(),
            start_router(),
            start_marketcap_updater(),
        ]
        if Config.TG_BOT_TOKEN:
            tasks.append(start_command_bot())
        await asyncio.gather(*tasks)
    finally:
        await close_client()
