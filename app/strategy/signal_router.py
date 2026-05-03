import asyncio
import time
from app.bus.redis_bus import consume
from app.strategy.validator import validate
from app.market.coin_classifier import classify
from app.strategy.tp_selector import get_tp
from app.exchange.executor import open_trade
from app.exchange.account import get_available_usdt
from app.strategy.position_manager import watch
from app.strategy import trade_history
from app.core.logger import logger

_busy = False
_busy_lock = asyncio.Lock()
_current_trade: str | None = None


def is_trading() -> bool:
    return _busy


async def _try_claim(symbol: str) -> bool:
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

        balance_before = await get_available_usdt()
        trade = await open_trade(symbol, tp)
        if not trade:
            return

        if balance_before <= 0:
            balance_before = trade.get("balance_before") or 0.0

        await trade_history.trade_opened(
            symbol=symbol,
            entry=trade["entry"],
            qty=trade["qty"],
            leverage=trade["leverage"],
            margin=trade.get("margin", 0.0),
            balance_before=balance_before,
            tp_pct=tp,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"{symbol} entry placed in {elapsed_ms:.0f}ms — watching to close")

        result = await watch(trade)
        await asyncio.sleep(1.0)
        balance_after = await get_available_usdt(force_refresh=True)
        await trade_history.trade_closed(result=result, balance_after=balance_after)
        logger.info(
            f"{symbol} closed ({result}) — balance {balance_before:.2f} → {balance_after:.2f}"
        )
    except Exception as e:
        logger.exception(f"Error handling {symbol}: {e}")
        try:
            bal = await get_available_usdt(force_refresh=True)
            await trade_history.trade_closed(result="ERROR", balance_after=bal)
        except Exception:
            pass
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
