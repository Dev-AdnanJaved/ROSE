import time
import asyncio
from app.exchange.binance_client import get_client
from app.core.config import Config
from app.core.logger import logger

_balance_cache: dict = {"value": 0.0, "ts": 0.0}
_lock = asyncio.Lock()
_hedge_mode: bool | None = None


async def detect_position_mode() -> bool:
    """Detects whether the futures account is in hedge (dual-side) mode."""
    global _hedge_mode
    if _hedge_mode is not None:
        return _hedge_mode
    try:
        client = await get_client()
        res = await client.futures_get_position_mode()
        _hedge_mode = bool(res.get("dualSidePosition"))
        logger.info(f"Account position mode: {'HEDGE' if _hedge_mode else 'ONE-WAY'}")
    except Exception as e:
        _hedge_mode = False
        logger.warning(f"position mode detect failed, assuming ONE-WAY: {e}")
    return _hedge_mode


def is_hedge_mode() -> bool:
    return bool(_hedge_mode)


async def has_open_positions() -> bool:
    try:
        client = await get_client()
        positions = await client.futures_position_information()
        for p in positions:
            if float(p.get("positionAmt", 0)) != 0:
                return True
    except Exception as e:
        logger.warning(f"open-position check failed: {e}")
    return False


async def get_open_position_symbols() -> list[str]:
    try:
        client = await get_client()
        positions = await client.futures_position_information()
        return [
            p["symbol"] for p in positions
            if float(p.get("positionAmt", 0)) != 0
        ]
    except Exception:
        return []


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
