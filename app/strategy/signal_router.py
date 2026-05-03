import asyncio
import time
from app.bus.redis_bus import consume
from app.strategy.validator import validate
from app.market.coin_classifier import classify
from app.strategy.tp_selector import get_tp
from app.exchange.executor import open_trade
from app.strategy.position_manager import watch
from app.core.logger import logger

_trade_lock = asyncio.Lock()
_current_trade: str | None = None


def is_trading() -> bool:
    return _current_trade is not None


async def _handle(symbol: str):
    global _current_trade

    if _trade_lock.locked() or _current_trade is not None:
        logger.info(
            f"{symbol} skipped — trade already in progress ({_current_trade})"
        )
        return

    async with _trade_lock:
        if _current_trade is not None:
            logger.info(f"{symbol} skipped — {_current_trade} still active")
            return
        _current_trade = symbol
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
            _current_trade = None


async def start_router():
    logger.info("Signal router started (single-trade mode)")
    while True:
        msg = await consume()
        symbol = msg.get("symbol")
        if not symbol:
            continue
        if _current_trade is not None:
            logger.info(
                f"Signal {symbol} dropped — {_current_trade} still open"
            )
            continue
        asyncio.create_task(_handle(symbol))
