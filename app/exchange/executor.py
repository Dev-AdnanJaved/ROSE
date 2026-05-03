import asyncio
from app.exchange.binance_client import get_client
from app.exchange import symbols
from app.core.config import Config
from app.core.logger import logger


async def _ensure_leverage_and_margin(client, symbol: str, leverage: int) -> bool:
    tasks = []
    if symbols.needs_leverage_set(symbol):
        tasks.append(("leverage", _set_leverage(client, symbol, leverage)))
    if symbols.needs_margin_set(symbol):
        tasks.append(("margin", _set_margin(client, symbol)))
    if not tasks:
        return True
    results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
    for (name, _), res in zip(tasks, results):
        if isinstance(res, Exception) or res is False:
            logger.error(f"{symbol} {name} setup failed: {res} — aborting trade")
            return False
    return True


async def _set_leverage(client, symbol, leverage) -> bool:
    await client.futures_change_leverage(symbol=symbol, leverage=leverage)
    symbols.mark_leverage_set(symbol)
    logger.info(f"{symbol} leverage set to {leverage}x")
    return True


async def _set_margin(client, symbol) -> bool:
    try:
        await client.futures_change_margin_type(
            symbol=symbol, marginType=Config.MARGIN_TYPE
        )
        symbols.mark_margin_set(symbol)
        return True
    except Exception as e:
        msg = str(e)
        if "No need to change margin type" in msg or "-4046" in msg:
            symbols.mark_margin_set(symbol)
            return True
        raise


async def open_trade(symbol: str, tp_pct: float):
    """
    Returns dict with entry, qty, tp_order_id, sl_order_id, leverage — or None on failure.
    """
    client = await get_client()

    if not symbols.is_tradable(symbol):
        logger.warning(f"{symbol} not a tradable USDT-M futures symbol — skipping")
        return None

    f = symbols.get_filters(symbol)
    max_lev = min(symbols.get_max_leverage(symbol), Config.MAX_LEVERAGE_CAP)

    try:
        mark_task = asyncio.create_task(_mark_price(client, symbol))
        ok = await _ensure_leverage_and_margin(client, symbol, max_lev)
        if not ok:
            mark_task.cancel()
            return None
        price = await mark_task
        if price <= 0:
            logger.error(f"{symbol} bad mark price")
            return None

        notional = Config.TRADE_SIZE * max_lev
        raw_qty = notional / price
        qty = symbols.round_qty(symbol, raw_qty)

        if qty < f["min_qty"] or qty <= 0:
            logger.error(f"{symbol} qty {qty} below minQty {f['min_qty']}")
            return None
        if f["min_notional"] and qty * price < f["min_notional"]:
            logger.error(
                f"{symbol} notional {qty*price:.4f} below minNotional {f['min_notional']}"
            )
            return None

        order = await client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quantity=qty,
            newOrderRespType="RESULT",
        )

        entry = _extract_avg(order, fallback=price)
        logger.info(f"OPENED {symbol} qty={qty} entry={entry} lev={max_lev}x")

        tp_id, sl_id = await _place_exit_brackets(client, symbol, entry, qty, tp_pct)

        return {
            "symbol": symbol,
            "entry": entry,
            "qty": qty,
            "leverage": max_lev,
            "tp_order_id": tp_id,
            "sl_order_id": sl_id,
        }

    except Exception as e:
        logger.exception(f"open_trade failed for {symbol}: {e}")
        return None


async def _mark_price(client, symbol):
    data = await client.futures_mark_price(symbol=symbol)
    return float(data["markPrice"])


def _extract_avg(order, fallback):
    avg = float(order.get("avgPrice") or 0)
    if avg > 0:
        return avg
    executed = float(order.get("executedQty") or 0)
    cum_quote = float(order.get("cumQuote") or 0)
    if executed > 0 and cum_quote > 0:
        return cum_quote / executed
    return fallback


async def _place_exit_brackets(client, symbol, entry, qty, tp_pct):
    tp_price = entry * (1 + tp_pct / 100)
    if Config.TP_LIMIT_OFFSET_BPS:
        tp_price *= 1 + Config.TP_LIMIT_OFFSET_BPS / 10_000
    tp_price = symbols.round_price(symbol, tp_price)

    sl_price = entry * (1 - Config.STOP_LOSS / 100)
    sl_price = symbols.round_price(symbol, sl_price)

    if Config.USE_LIMIT_TP:
        tp_coro = client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="LIMIT",
            timeInForce="GTC",
            quantity=qty,
            price=tp_price,
            reduceOnly=True,
        )
    else:
        tp_coro = client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="TAKE_PROFIT_MARKET",
            stopPrice=tp_price,
            closePosition=True,
        )

    sl_coro = client.futures_create_order(
        symbol=symbol,
        side="SELL",
        type="STOP_MARKET",
        stopPrice=sl_price,
        closePosition=True,
    )

    tp_res, sl_res = await asyncio.gather(tp_coro, sl_coro, return_exceptions=True)

    tp_id = sl_id = None
    if isinstance(tp_res, Exception):
        logger.error(f"{symbol} TP order failed: {tp_res}")
    else:
        tp_id = tp_res.get("orderId")
        logger.info(f"{symbol} TP @ {tp_price} (id={tp_id})")

    if isinstance(sl_res, Exception):
        logger.error(f"{symbol} SL order failed: {sl_res}")
    else:
        sl_id = sl_res.get("orderId")
        logger.info(f"{symbol} SL @ {sl_price} (id={sl_id})")

    return tp_id, sl_id
