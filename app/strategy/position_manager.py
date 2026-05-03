import asyncio
from app.exchange.binance_client import get_client
from app.core.logger import logger


async def watch(trade: dict):
    """
    Watches the TP and SL orders. When one fills, cancels the other.
    Falls back to position-zero detection if both order ids are missing.
    """
    client = await get_client()
    symbol = trade["symbol"]
    tp_id = trade.get("tp_order_id")
    sl_id = trade.get("sl_order_id")

    delay = 0.5
    while True:
        try:
            tp_status, sl_status = await asyncio.gather(
                _order_status(client, symbol, tp_id),
                _order_status(client, symbol, sl_id),
                return_exceptions=True,
            )

            tp_filled = _is_filled(tp_status)
            sl_filled = _is_filled(sl_status)

            if tp_filled:
                logger.info(f"{symbol} TP FILLED — cancelling SL")
                await _cancel(client, symbol, sl_id)
                return "TP"

            if sl_filled:
                logger.info(f"{symbol} SL FILLED — cancelling TP")
                await _cancel(client, symbol, tp_id)
                return "SL"

            if tp_id is None and sl_id is None:
                if await _position_closed(client, symbol):
                    logger.info(f"{symbol} position closed (no bracket orders)")
                    return "CLOSED"

        except Exception as e:
            logger.warning(f"{symbol} watch error: {e}")

        await asyncio.sleep(delay)
        delay = min(delay * 1.2, 2.0)


async def _order_status(client, symbol, order_id):
    if order_id is None:
        return None
    return await client.futures_get_order(symbol=symbol, orderId=order_id)


def _is_filled(status):
    if not status or isinstance(status, Exception):
        return False
    return status.get("status") == "FILLED"


async def _cancel(client, symbol, order_id):
    if order_id is None:
        return
    try:
        await client.futures_cancel_order(symbol=symbol, orderId=order_id)
    except Exception as e:
        logger.warning(f"{symbol} cancel order {order_id} failed: {e}")


async def _position_closed(client, symbol):
    try:
        positions = await client.futures_position_information(symbol=symbol)
        for p in positions:
            if float(p.get("positionAmt", 0)) != 0:
                return False
        return True
    except Exception:
        return False
