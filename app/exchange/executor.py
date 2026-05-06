import asyncio
from app.exchange.binance_client import get_client
from app.exchange import symbols
from app.exchange.account import get_available_usdt, invalidate_balance_cache, is_hedge_mode
from app.core.config import Config
from app.core.logger import logger


def _side_kwargs():
    """Adds positionSide=LONG when account is in hedge mode."""
    return {"positionSide": "LONG"} if is_hedge_mode() else {}


def _close_kwargs():
    """For closing a long: hedge mode needs positionSide=LONG; one-way uses reduceOnly."""
    if is_hedge_mode():
        return {"positionSide": "LONG"}
    return {"reduceOnly": True}


async def _ensure_leverage_and_margin(client, symbol: str, leverage: int) -> int:
    """Returns the actually-set leverage (>=1), or 0 on total failure."""
    margin_task = None
    if symbols.needs_margin_set(symbol):
        margin_task = asyncio.create_task(_set_margin(client, symbol))

    if symbols.needs_leverage_set(symbol):
        applied = await _set_leverage_with_fallback(client, symbol, leverage)
    else:
        applied = leverage

    if margin_task is not None:
        try:
            await margin_task
        except Exception as e:
            logger.warning(
                f"{symbol} margin type setup failed: {e} — "
                f"continuing with current margin type (trade will still work)"
            )
            symbols.mark_margin_set(symbol)

    return applied


async def _set_leverage_with_fallback(client, symbol, leverage) -> int:
    """Try the configured leverage ladder, starting at the requested level or below."""
    ladder = [v for v in Config.LEVERAGE_LADDER if v <= leverage]
    if not ladder or ladder[0] != leverage:
        ladder = [leverage] + ladder
    seen = set()
    ordered = []
    for v in ladder:
        if v >= 1 and v not in seen:
            seen.add(v)
            ordered.append(v)

    last_err = None
    for attempt in ordered:
        try:
            await client.futures_change_leverage(symbol=symbol, leverage=attempt)
            symbols.mark_leverage_set(symbol)
            if attempt != leverage:
                logger.warning(
                    f"{symbol} leverage set to {attempt}x (requested {leverage}x — fallback)"
                )
            else:
                logger.info(f"{symbol} leverage set to {attempt}x")
            return attempt
        except Exception as e:
            last_err = e
            logger.warning(f"{symbol} leverage {attempt}x rejected: {e}")

    logger.error(f"{symbol} leverage setup failed at every level: {last_err}")
    return 0


async def _set_margin(client, symbol) -> bool:
    """Set margin type. Tries multiple call styles to handle python-binance quirks."""
    margin_type = Config.MARGIN_TYPE

    async def _try(call):
        await call()
        symbols.mark_margin_set(symbol)
        return True

    attempts = [
        lambda: client.futures_change_margin_type(symbol=symbol, marginType=margin_type),
        lambda: client._request_futures_api(
            "post", "marginType", True,
            data={"symbol": symbol, "marginType": margin_type},
        ),
    ]

    last_err = None
    for call in attempts:
        try:
            return await _try(call)
        except Exception as e:
            msg = str(e)
            if "No need to change margin type" in msg or "-4046" in msg:
                symbols.mark_margin_set(symbol)
                return True
            last_err = e
            logger.warning(f"{symbol} margin attempt failed ({msg[:120]}); trying next style")

    raise last_err if last_err else RuntimeError("margin setup failed")


async def open_trade(symbol: str, tp_pct: float):
    """
    Returns dict with entry, qty, tp_order_id, sl_order_id, leverage — or None on failure.
    """
    client = await get_client()

    if not symbols.is_tradable(symbol):
        logger.warning(f"{symbol} not a tradable USDT-M futures symbol — skipping")
        return {"error": "not a tradable USDT-M futures symbol"}

    f = symbols.get_filters(symbol)
    max_lev = min(symbols.get_max_leverage(symbol), Config.MAX_LEVERAGE_CAP)

    try:
        mark_task = asyncio.create_task(_mark_price(client, symbol))
        bal_task = asyncio.create_task(get_available_usdt()) \
            if Config.SIZING_MODE == "PERCENT" else None
        applied_lev = await _ensure_leverage_and_margin(client, symbol, max_lev)
        if applied_lev <= 0:
            mark_task.cancel()
            if bal_task:
                bal_task.cancel()
            return {"error": "leverage/margin setup failed (every ladder step rejected)"}
        if applied_lev != max_lev:
            max_lev = applied_lev
        price = await mark_task
        if price <= 0:
            logger.error(f"{symbol} bad mark price")
            if bal_task:
                bal_task.cancel()
            return {"error": "mark price unavailable"}

        if Config.SIZING_MODE == "PERCENT":
            balance = await bal_task
            if balance <= 0:
                logger.error(f"{symbol} no available USDT balance")
                return {"error": "no available USDT balance"}
            margin = balance * Config.TRADE_MARGIN_PCT / 100
            logger.info(
                f"{symbol} balance={balance:.2f} USDT × {Config.TRADE_MARGIN_PCT}% "
                f"= margin {margin:.2f} USDT"
            )
        else:
            margin = Config.TRADE_SIZE

        notional = margin * max_lev
        raw_qty = notional / price
        qty = symbols.round_qty(symbol, raw_qty)

        if qty < f["min_qty"] or qty <= 0:
            logger.error(f"{symbol} qty {qty} below minQty {f['min_qty']}")
            return {"error": f"qty {qty} below minQty {f['min_qty']} (margin too small for this coin)"}
        if f["min_notional"] and qty * price < f["min_notional"]:
            logger.error(
                f"{symbol} notional {qty*price:.4f} below minNotional {f['min_notional']}"
            )
            return {"error": f"notional ${qty*price:.2f} below Binance minNotional ${f['min_notional']} (increase TRADE_MARGIN_PCT)"}

        order = await client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quantity=qty,
            newOrderRespType="RESULT",
            **_side_kwargs(),
        )

        entry = _extract_avg(order, fallback=price)
        invalidate_balance_cache()
        logger.info(f"OPENED {symbol} qty={qty} entry={entry} lev={max_lev}x margin={margin:.2f}")

        tp_id, sl_id = await _place_exit_brackets(client, symbol, entry, qty, tp_pct, max_lev)

        return {
            "symbol": symbol,
            "entry": entry,
            "qty": qty,
            "leverage": max_lev,
            "margin": margin,
            "balance_before": balance if Config.SIZING_MODE == "PERCENT" else None,
            "tp_pct": tp_pct,
            "tp_order_id": tp_id,
            "sl_order_id": sl_id,
        }

    except Exception as e:
        logger.exception(f"open_trade failed for {symbol}: {e}")
        return {"error": str(e)[:200]}


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


async def _place_exit_brackets(client, symbol, entry, qty, tp_pct, leverage):
    tp_price = entry * (1 + tp_pct / 100)
    if Config.TP_LIMIT_OFFSET_BPS:
        tp_price *= 1 + Config.TP_LIMIT_OFFSET_BPS / 10_000
    tp_price = symbols.round_price(symbol, tp_price)

    sl_price_task = asyncio.create_task(_compute_sl_price(client, symbol, entry, leverage))
    tp_task = asyncio.create_task(_place_tp(client, symbol, qty, tp_price))

    sl_price = await sl_price_task
    sl_price = symbols.round_price(symbol, sl_price)
    sl_task = asyncio.create_task(_place_sl(client, symbol, sl_price))

    tp_id, sl_id = await asyncio.gather(tp_task, sl_task)

    if sl_id is None:
        existing = await _find_existing_sl(client, symbol)
        if existing is not None:
            logger.warning(f"{symbol} SL was actually placed (found via open orders): id={existing}")
            sl_id = existing
        else:
            logger.critical(
                f"{symbol} SL could not be confirmed — LEAVING POSITION OPEN with TP only. "
                f"Manage manually on Binance!"
            )

    if tp_id is None:
        logger.error(
            f"{symbol} TP failed after retries — position protected by SL, leaving open"
        )

    return tp_id, sl_id


async def _place_tp(client, symbol, qty, tp_price, attempts=4):
    delay = 0.3
    for i in range(1, attempts + 1):
        try:
            if Config.USE_LIMIT_TP:
                res = await client.futures_create_order(
                    symbol=symbol, side="SELL", type="LIMIT",
                    timeInForce="GTC", quantity=qty, price=str(tp_price),
                    **_close_kwargs(),
                )
            else:
                kw = {"positionSide": "LONG", "closePosition": True} if is_hedge_mode() else {"closePosition": True}
                res = await client.futures_create_order(
                    symbol=symbol, side="SELL", type="TAKE_PROFIT_MARKET",
                    stopPrice=str(tp_price), workingType="MARK_PRICE",
                    **kw,
                )
            logger.debug(f"{symbol} TP raw response: {res}")
            oid = _extract_order_id(res)
            if oid is not None:
                logger.info(f"{symbol} TP @ {tp_price} placed (id={oid}, attempt {i})")
                return oid
            logger.warning(f"{symbol} TP attempt {i}/{attempts} — no orderId in response: {res}")
        except Exception as e:
            logger.warning(f"{symbol} TP attempt {i}/{attempts} failed: {e}")
        if i < attempts:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 2.0)
    return None


async def _place_sl(client, symbol, sl_price, attempts=5):
    delay = 0.3
    for i in range(1, attempts + 1):
        try:
            kw = {"positionSide": "LONG", "closePosition": True} if is_hedge_mode() else {"closePosition": True}
            res = await client.futures_create_order(
                symbol=symbol, side="SELL", type="STOP_MARKET",
                stopPrice=str(sl_price), workingType="MARK_PRICE",
                **kw,
            )
            logger.debug(f"{symbol} SL raw response: {res}")
            oid = _extract_order_id(res)
            if oid is not None:
                verified = await _verify_order_exists(client, symbol, oid, "SL", i)
                if verified is not None:
                    return verified
            existing = await _find_existing_sl(client, symbol)
            if existing is not None:
                logger.info(f"{symbol} SL already exists on Binance (id={existing}) — using it")
                return existing
            logger.warning(f"{symbol} SL attempt {i}/{attempts} — order not confirmed on Binance")
        except Exception as e:
            msg = str(e)
            if "-4130" in msg or "is existing" in msg:
                existing = await _find_existing_sl(client, symbol)
                if existing is not None:
                    logger.info(f"{symbol} SL already exists on Binance (id={existing}) — using it (got -4130)")
                    return existing
                logger.warning(f"{symbol} got -4130 but no SL found on Binance — odd state")
            else:
                logger.warning(f"{symbol} SL attempt {i}/{attempts} failed: {e}")
        if i < attempts:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 2.0)
    return None


async def _find_existing_sl(client, symbol):
    """Query open orders, return the orderId of any existing SELL stop on this symbol."""
    try:
        orders = await client.futures_get_open_orders(symbol=symbol)
        logger.info(f"{symbol} open orders found: {len(orders)} — types: {[o.get('type') for o in orders]}")
        for o in orders:
            otype = (o.get("type") or "").upper()
            side = (o.get("side") or "").upper()
            if side == "SELL" and ("STOP" in otype):
                logger.info(f"{symbol} matched existing SL: {o}")
                return o.get("orderId")
        logger.warning(f"{symbol} no SELL stop found among open orders: {orders}")
    except Exception as e:
        logger.warning(f"{symbol} _find_existing_sl query failed: {e}")
    return None


def _extract_order_id(res):
    if not res:
        return None
    oid = res.get("orderId")
    if oid is not None and oid != 0:
        return oid
    for key in ("orderID", "order_id"):
        v = res.get(key)
        if v is not None and v != 0:
            return v
    cid = res.get("clientOrderId")
    if cid:
        return cid
    return None


async def _verify_order_exists(client, symbol, oid, label, attempt):
    try:
        if isinstance(oid, int) or (isinstance(oid, str) and oid.isdigit()):
            order = await client.futures_get_order(symbol=symbol, orderId=int(oid))
        elif isinstance(oid, str):
            order = await client.futures_get_order(symbol=symbol, origClientOrderId=oid)
        else:
            logger.info(f"{symbol} {label} @ placed (id={oid}, attempt {attempt}) — unverified")
            return oid
        status = order.get("status", "UNKNOWN")
        real_id = order.get("orderId", oid)
        logger.info(f"{symbol} {label} verified on Binance (id={real_id}, status={status}, attempt {attempt})")
        return real_id
    except Exception as e:
        logger.warning(f"{symbol} {label} verify failed for id={oid}: {e}")
        return None


async def _emergency_close(client, symbol, qty):
    for i in range(1, 6):
        try:
            actual_qty = await _current_position_qty(client, symbol)
            close_qty = actual_qty if actual_qty > 0 else qty
            if close_qty <= 0:
                logger.warning(f"{symbol} no position to close")
                return True
            await client.futures_create_order(
                symbol=symbol, side="SELL", type="MARKET",
                quantity=close_qty, **_close_kwargs(),
            )
            logger.warning(f"{symbol} emergency MARKET close succeeded qty={close_qty} (attempt {i})")
            return True
        except Exception as e:
            logger.error(f"{symbol} emergency close attempt {i} failed: {e}")
            await asyncio.sleep(min(0.5 * i, 3.0))
    logger.critical(f"{symbol} EMERGENCY CLOSE FAILED — MANUAL INTERVENTION REQUIRED")
    return False


async def _current_position_qty(client, symbol):
    try:
        positions = await client.futures_position_information(symbol=symbol)
        for p in positions:
            amt = float(p.get("positionAmt", 0))
            if is_hedge_mode() and p.get("positionSide") != "LONG":
                continue
            if amt > 0:
                return amt
    except Exception:
        pass
    return 0.0


async def _compute_sl_price(client, symbol, entry, leverage):
    """SL just above the actual liquidation price (LIQUIDATION mode), or fixed % (FIXED)."""
    if Config.SL_MODE == "FIXED":
        return entry * (1 - Config.STOP_LOSS / 100)

    liq = await _fetch_liquidation_price(client, symbol)
    if liq and liq > 0:
        buffer = Config.SL_LIQUIDATION_BUFFER_PCT / 100
        sl = liq * (1 + buffer)
        if sl >= entry:
            logger.warning(
                f"{symbol} liquidation-based SL ({sl}) >= entry ({entry}); "
                f"falling back to fixed STOP_LOSS"
            )
            return entry * (1 - Config.STOP_LOSS / 100)
        logger.info(f"{symbol} liq={liq} -> SL={sl} (buffer {Config.SL_LIQUIDATION_BUFFER_PCT}%)")
        return sl

    approx_liq = entry * (1 - 1.0 / max(leverage, 1))
    sl = approx_liq * (1 + Config.SL_LIQUIDATION_BUFFER_PCT / 100)
    logger.warning(f"{symbol} no liq price from Binance; using approx SL={sl}")
    return sl


async def _fetch_liquidation_price(client, symbol):
    try:
        positions = await client.futures_position_information(symbol=symbol)
        for p in positions:
            amt = float(p.get("positionAmt", 0))
            if is_hedge_mode() and p.get("positionSide") != "LONG":
                continue
            if amt > 0:
                liq = float(p.get("liquidationPrice", 0))
                if liq > 0:
                    return liq
    except Exception as e:
        logger.warning(f"{symbol} liquidation price fetch failed: {e}")
    return None
