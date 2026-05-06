import asyncio
from app.exchange.binance_client import get_client
from app.exchange.account import is_hedge_mode
from app.core.logger import logger


def _is_numeric_id(order_id):
    if order_id is None:
        return False
    if isinstance(order_id, int) and not isinstance(order_id, bool):
        return True
    return isinstance(order_id, str) and order_id.isdigit()


def _is_client_id(order_id):
    if order_id is None:
        return False
    return isinstance(order_id, str) and not order_id.isdigit() and order_id != "OK_NO_ID"


async def watch(trade: dict):
    """
    Watches the TP/SL orders AND the actual position size. Exits when:
      - TP order fills → cancel SL
      - SL order fills → cancel TP
      - Position is flat (any reason: manual close, liquidation, both orders gone) → return
    """
    client = await get_client()
    symbol = trade["symbol"]
    tp_id = trade.get("tp_order_id")
    sl_id = trade.get("sl_order_id")

    delay = 0.5
    while True:
        try:
            tp_status, sl_status, pos_amt = await asyncio.gather(
                _order_status(client, symbol, tp_id),
                _order_status(client, symbol, sl_id),
                _position_amt(client, symbol),
                return_exceptions=True,
            )

            if _is_filled(tp_status):
                logger.info(f"{symbol} TP FILLED — cancelling SL")
                await _cancel(client, symbol, sl_id)
                return "TP"

            if _is_filled(sl_status):
                logger.info(f"{symbol} SL FILLED — cancelling TP")
                await _cancel(client, symbol, tp_id)
                return "SL"

            if isinstance(pos_amt, (int, float)) and pos_amt == 0:
                logger.info(f"{symbol} position flat — cancelling residual orders")
                await asyncio.gather(
                    _cancel(client, symbol, tp_id),
                    _cancel(client, symbol, sl_id),
                    return_exceptions=True,
                )
                return "CLOSED"

        except Exception as e:
            logger.warning(f"{symbol} watch error: {e}")

        await asyncio.sleep(delay)
        delay = min(delay * 1.2, 2.0)


async def _order_status(client, symbol, order_id):
    """Returns dict with at least {status: ...}. For algo/conditional orders the
    regular endpoint returns -2013; in that case we look in the conditional bucket.
    Algo orders use 'algoStatus' which we normalize to 'status'."""
    if order_id is None:
        return None
    try:
        if _is_numeric_id(order_id):
            return await client.futures_get_order(symbol=symbol, orderId=int(order_id))
        if _is_client_id(order_id):
            return await client.futures_get_order(symbol=symbol, origClientOrderId=order_id)
        return None
    except Exception as e:
        if "-2013" not in str(e):
            return None
    try:
        res = await client._request_futures_api(
            "get", "algo/futures/openOrders", True, data={"symbol": symbol}
        )
        orders = res.get("orders") if isinstance(res, dict) else (res or [])
        for o in orders or []:
            if str(o.get("algoId")) == str(order_id) or o.get("clientAlgoId") == str(order_id):
                st = o.get("algoStatus") or o.get("status")
                return {**o, "status": st}
    except Exception:
        pass
    return None


def _is_filled(status):
    if not status or isinstance(status, Exception):
        return False
    return status.get("status") == "FILLED"


async def _cancel(client, symbol, order_id):
    if order_id is None:
        return
    try:
        if _is_numeric_id(order_id):
            await client.futures_cancel_order(symbol=symbol, orderId=int(order_id))
            return
        if _is_client_id(order_id):
            await client.futures_cancel_order(symbol=symbol, origClientOrderId=order_id)
            return
        return
    except Exception as e:
        msg = str(e)
        if "Unknown order" in msg or "-2011" in msg:
            return
        try:
            data = {"symbol": symbol}
            if _is_numeric_id(order_id):
                data["algoId"] = int(order_id)
            else:
                data["clientAlgoId"] = order_id
            await client._request_futures_api("delete", "algo/futures/order", True, data=data)
            logger.info(f"{symbol} cancelled algo order {order_id} via algo endpoint")
            return
        except Exception as e2:
            msg2 = str(e2)
            if "Unknown order" in msg2 or "-2011" in msg2:
                return
            logger.warning(f"{symbol} cancel order {order_id} failed: {e} / algo: {e2}")


async def _position_amt(client, symbol) -> float:
    try:
        positions = await client.futures_position_information(symbol=symbol)
        for p in positions:
            if is_hedge_mode() and p.get("positionSide") != "LONG":
                continue
            amt = float(p.get("positionAmt", 0))
            if is_hedge_mode():
                if p.get("positionSide") == "LONG":
                    return abs(amt)
            else:
                if amt != 0:
                    return abs(amt)
        return 0.0
    except Exception:
        return -1.0
