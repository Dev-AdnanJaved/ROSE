"""Pre-warmed Binance USDT-M futures symbol metadata cache."""
import asyncio
from app.exchange.binance_client import get_client
from app.core.logger import logger

_filters: dict[str, dict] = {}
_max_leverage: dict[str, int] = {}
_leverage_set: set[str] = set()
_margin_set: set[str] = set()
_ready = asyncio.Event()


async def warmup():
    """Load exchangeInfo + leverage brackets for every USDT-M futures symbol once."""
    client = await get_client()
    info, brackets = await asyncio.gather(
        client.futures_exchange_info(),
        client.futures_leverage_bracket(),
    )

    for s in info["symbols"]:
        if s.get("status") != "TRADING":
            continue
        if s.get("quoteAsset") != "USDT":
            continue
        sym = s["symbol"]
        step = tick = 0.0
        min_qty = min_notional = 0.0
        for f in s["filters"]:
            t = f["filterType"]
            if t == "LOT_SIZE":
                step = float(f["stepSize"])
                min_qty = float(f["minQty"])
            elif t == "PRICE_FILTER":
                tick = float(f["tickSize"])
            elif t in ("MIN_NOTIONAL", "NOTIONAL"):
                min_notional = float(f.get("notional") or f.get("minNotional") or 0)
        _filters[sym] = {
            "step": step,
            "tick": tick,
            "min_qty": min_qty,
            "min_notional": min_notional,
            "qty_precision": _precision(step),
            "price_precision": _precision(tick),
        }

    for entry in brackets:
        sym = entry["symbol"]
        if sym not in _filters:
            continue
        max_lev = max((b["initialLeverage"] for b in entry["brackets"]), default=1)
        _max_leverage[sym] = int(max_lev)

    _ready.set()
    logger.info(f"Symbol cache warmed: {len(_filters)} USDT-M futures symbols")


async def wait_ready(timeout: float = 10.0) -> bool:
    try:
        await asyncio.wait_for(_ready.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False


def is_tradable(symbol: str) -> bool:
    return symbol in _filters


def get_filters(symbol: str) -> dict | None:
    return _filters.get(symbol)


def get_max_leverage(symbol: str) -> int:
    return _max_leverage.get(symbol, 1)


def mark_leverage_set(symbol: str) -> None:
    _leverage_set.add(symbol)


def needs_leverage_set(symbol: str) -> bool:
    return symbol not in _leverage_set


def mark_margin_set(symbol: str) -> None:
    _margin_set.add(symbol)


def needs_margin_set(symbol: str) -> bool:
    return symbol not in _margin_set


def round_qty(symbol: str, qty: float) -> float:
    f = _filters.get(symbol)
    if not f or f["step"] <= 0:
        return qty
    n = int(qty / f["step"])
    return round(n * f["step"], f["qty_precision"])


def round_price(symbol: str, price: float) -> float:
    f = _filters.get(symbol)
    if not f or f["tick"] <= 0:
        return price
    n = round(price / f["tick"])
    return round(n * f["tick"], f["price_precision"])


def _precision(step: float) -> int:
    if step <= 0:
        return 0
    s = f"{step:.10f}".rstrip("0").rstrip(".")
    return len(s.split(".")[1]) if "." in s else 0
