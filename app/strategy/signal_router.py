import asyncio
import time
from app.bus.redis_bus import consume
from app.strategy.validator import validate
from app.market.coin_classifier import classify
from app.strategy.tp_selector import get_tp
from app.exchange.executor import open_trade
from app.strategy.position_manager import watch
from app.core.logger import logger

_active: set[str] = set()


async def _handle(symbol: str):
    if symbol in _active:
        logger.info(f"{symbol} already active, skipping")
        return
    _active.add(symbol)
    t0 = time.perf_counter()
    try:
        valid_task = asyncio.create_task(validate(symbol))
        cap_task = asyncio.create_task(classify(symbol))
        valid, cap = await asyncio.gather(valid_task, cap_task)

        if not valid:
            logger.info(f"{symbol} failed validation")
            return

        tp = get_tp(cap)
        logger.info(f"{symbol} cap={cap} tp={tp}%")

        trade = await open_trade(symbol, tp)
        if not trade:
            return

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"{symbol} entry placed in {elapsed_ms:.0f}ms")

        await watch(trade)
    except Exception as e:
        logger.exception(f"Error handling {symbol}: {e}")
    finally:
        _active.discard(symbol)


async def start_router():
    logger.info("Signal router started")
    while True:
        msg = await consume()
        symbol = msg.get("symbol")
        if symbol:
            asyncio.create_task(_handle(symbol))
