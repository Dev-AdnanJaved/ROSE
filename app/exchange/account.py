import time
import asyncio
from app.exchange.binance_client import get_client
from app.core.config import Config
from app.core.logger import logger

_balance_cache: dict = {"value": 0.0, "ts": 0.0}
_lock = asyncio.Lock()


async def get_available_usdt(force_refresh: bool = False) -> float:
    """Returns available USDT in futures wallet, cached briefly to keep signals fast."""
    now = time.time()
    if (
        not force_refresh
        and _balance_cache["value"] > 0
        and now - _balance_cache["ts"] < Config.BALANCE_CACHE_SECONDS
    ):
        return _balance_cache["value"]

    async with _lock:
        now = time.time()
        if (
            not force_refresh
            and _balance_cache["value"] > 0
            and now - _balance_cache["ts"] < Config.BALANCE_CACHE_SECONDS
        ):
            return _balance_cache["value"]
        try:
            client = await get_client()
            balances = await client.futures_account_balance()
            for b in balances:
                if b.get("asset") == "USDT":
                    val = float(b.get("availableBalance", 0))
                    _balance_cache["value"] = val
                    _balance_cache["ts"] = time.time()
                    return val
        except Exception as e:
            logger.error(f"balance fetch failed: {e}")
        return _balance_cache["value"]


def invalidate_balance_cache():
    _balance_cache["ts"] = 0.0
