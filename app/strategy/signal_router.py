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
from app.telegram.command_bot import notify_bg
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


def _fmt_open(trade, tp_pct, balance_before):
    sl_ok = bool(trade.get("sl_order_id"))
    tp_ok = bool(trade.get("tp_order_id"))
    sl_txt = "✅" if sl_ok else "⚠️ NOT PLACED — manage manually!"
    tp_txt = "✅" if tp_ok else "⚠️ NOT PLACED"
    entry = trade["entry"]
    tp_price = entry * (1 + tp_pct / 100)
    warning = "" if sl_ok else "\n\n🚨 *NO STOP LOSS* — set one on Binance NOW!"
    return (
        f"🟢 *TRADE OPENED*\n"
        f"Symbol: `{trade['symbol']}`\n"
        f"Side: `LONG`\n"
        f"Entry: `{entry}`\n"
        f"Qty: `{trade['qty']}`\n"
        f"Leverage: `{trade['leverage']}x`\n"
        f"Margin: `{trade.get('margin', 0):.2f}` USDT\n"
        f"Notional: `{trade['qty'] * entry:.2f}` USDT\n"
        f"TP target: `{tp_pct}%` (≈ `{tp_price:.6f}`)\n"
        f"TP order: {tp_txt}\n"
        f"SL order: {sl_txt}\n"
        f"Balance before: `{balance_before:.2f}` USDT"
        f"{warning}"
    )


def _fmt_close(symbol, result, balance_before, balance_after, duration_sec):
    pnl = balance_after - balance_before
    pct = (pnl / balance_before * 100) if balance_before else 0
    if result == "TP":
        head = "🎯 *TAKE PROFIT HIT*"
    elif result == "SL":
        head = "🛑 *STOP LOSS HIT*"
    elif result == "CLOSED":
        head = "🔒 *POSITION CLOSED*"
    else:
        head = f"⚠️ *TRADE ENDED ({result})*"
    sign = "✅" if pnl >= 0 else "❌"
    return (
        f"{head}\n"
        f"Symbol: `{symbol}`\n"
        f"{sign} PnL: `{pnl:+.4f}` USDT (`{pct:+.2f}%`)\n"
        f"Balance: `{balance_before:.2f} → {balance_after:.2f}` USDT\n"
        f"Duration: `{duration_sec:.1f}s`"
    )


async def _handle(symbol: str):
    t0 = time.perf_counter()
    try:
        valid, cap = await asyncio.gather(validate(symbol), classify(symbol))
        if not valid:
            logger.info(f"{symbol} failed validation")
            notify_bg(f"⚠️ `{symbol}` failed validation — skipped")
            return

        tp = get_tp(cap)
        logger.info(f"{symbol} cap={cap} tp={tp}%")

        balance_before = await get_available_usdt()
        trade = await open_trade(symbol, tp)
        if not trade or trade.get("error"):
            reason = (trade or {}).get("error", "unknown error")
            notify_bg(f"❌ *Trade failed* `{symbol}`\nReason: `{reason}`")
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
        notify_bg(_fmt_open(trade, tp, balance_before) + f"\nLatency: `{elapsed_ms:.0f}ms`")

        opened_at = time.time()
        result = await watch(trade)
        await asyncio.sleep(1.0)
        try:
            from app.exchange.executor import cleanup_stale_sl_orders
            n = await cleanup_stale_sl_orders(symbol)
            if n:
                logger.info(f"{symbol} cleaned up {n} stale SL order(s) after close")
        except Exception as ce:
            logger.warning(f"{symbol} post-close cleanup failed: {ce}")
        balance_after = await get_available_usdt(force_refresh=True)
        duration = time.time() - opened_at
        await trade_history.trade_closed(result=result, balance_after=balance_after)
        logger.info(
            f"{symbol} closed ({result}) — balance {balance_before:.2f} → {balance_after:.2f}"
        )
        notify_bg(_fmt_close(symbol, result, balance_before, balance_after, duration))
    except Exception as e:
        logger.exception(f"Error handling {symbol}: {e}")
        notify_bg(f"💥 `{symbol}` ERROR: `{str(e)[:200]}`")
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
            notify_bg(f"⏭️ Signal `{symbol}` dropped — `{_current_trade}` still open")
            continue
        asyncio.create_task(_handle(symbol))
