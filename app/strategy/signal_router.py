import asyncio
import time
from app.bus.redis_bus import consume
from app.strategy.validator import validate
from app.market.coin_classifier import classify
from app.strategy.tp_selector import get_tp
from app.exchange.executor import open_trade
from app.strategy.position_manager import watch
from app.core.logger import logger

_busy = False
_busy_lock = asyncio.Lock()
_current_trade: str | None = None


def is_trading() -> bool:
    return _busy


async def _try_claim(symbol: str) -> bool:
    """Atomic single-trade gate. Returns True if this signal got the slot."""
    global _busy, _current_trade
    async with _busy_lock:
        if _busy:
            return False
        _busy = True
        _current_trade = symbol
        return True


async def _release():
    global _busy, _current_trade
    async with _busy_lock:
        _busy = False
        _current_trade = None


async def _handle(symbol: str):
    t0 = time.perf_counter()
    try:
        valid, cap = await asyncio.gather(validate(symbol), classify(symbol))
        if not valid:
            logger.info(f"{symbol} failed validation")
            return

        tp = get_tp(cap)
        logger.info(f"{symbol} cap={cap} tp={tp}%")

        trade = await open_trade(symbol, tp)
        if not trade:
            return

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"{symbol} entry placed in {elapsed_ms:.0f}ms — watching to close")

        result = await watch(trade)
        logger.info(f"{symbol} closed ({result}) — ready for next signal")
    except Exception as e:
        logger.exception(f"Error handling {symbol}: {e}")
    finally:
        await _release()


async def start_router():
    logger.info("Signal router started (single-trade mode)")
    while True:
        msg = await consume()
        symbol = msg.get("symbol")
        if not symbol:
            continue
        claimed = await _try_claim(symbol)
        if not claimed:
            logger.info(f"Signal {symbol} dropped — {_current_trade} still open")
            continue
        asyncio.create_task(_handle(symbol))
