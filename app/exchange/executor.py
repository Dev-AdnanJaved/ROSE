from app.exchange.binance_client import get_client
from app.core.config import Config
from app.core.logger import logger


_symbol_filters = {}
_valid_symbols = None


async def _load_exchange_info(client):
    global _valid_symbols
    info = await client.futures_exchange_info()
    _valid_symbols = set()
    for s in info["symbols"]:
        if s.get("status") != "TRADING":
            continue
        sym = s["symbol"]
        _valid_symbols.add(sym)
        step = 0.0
        min_qty = 0.0
        for f in s["filters"]:
            if f["filterType"] == "LOT_SIZE":
                step = float(f["stepSize"])
                min_qty = float(f["minQty"])
        _symbol_filters[sym] = (step, min_qty)


async def _ensure_loaded(client):
    if _valid_symbols is None:
        await _load_exchange_info(client)


def _round_step(qty, step):
    if step <= 0:
        return qty
    s = f"{step:.10f}".rstrip("0").rstrip(".")
    precision = len(s.split(".")[1]) if "." in s else 0
    n = int(qty / step)
    return round(n * step, precision)


async def _mark_price(client, symbol):
    data = await client.futures_mark_price(symbol=symbol)
    return float(data["markPrice"])


async def open_trade(symbol):
    client = await get_client()

    try:
        await _ensure_loaded(client)

        if symbol not in _valid_symbols:
            logger.warning(f"{symbol} is not a tradable Binance futures symbol, skipping")
            return None, None

        price = await _mark_price(client, symbol)
        if price <= 0:
            logger.error(f"{symbol} invalid mark price")
            return None, None

        step, min_qty = _symbol_filters.get(symbol, (0.0, 0.0))
        raw_qty = Config.TRADE_SIZE / price
        qty = _round_step(raw_qty, step) if step > 0 else raw_qty

        if qty < min_qty or qty <= 0:
            logger.error(
                f"{symbol} qty {qty} below minQty {min_qty} for trade size {Config.TRADE_SIZE}"
            )
            return None, None

        order = await client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quantity=qty,
        )

        avg = float(order.get("avgPrice") or 0)
        if avg <= 0:
            executed = float(order.get("executedQty") or 0)
            cum_quote = float(order.get("cumQuote") or 0)
            if executed > 0 and cum_quote > 0:
                avg = cum_quote / executed
            else:
                avg = price

        logger.info(f"OPENED {symbol} qty={qty} entry={avg}")
        return avg, qty

    except Exception as e:
        logger.exception(f"open_trade failed for {symbol}: {e}")
        return None, None
