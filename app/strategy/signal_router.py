import json
import asyncio
from app.bus.redis_bus import subscribe
from app.strategy.validator import validate
from app.market.coin_classifier import classify
from app.strategy.tp_selector import get_tp
from app.exchange.executor import open_trade
from app.strategy.position_manager import manage
from app.core.logger import logger

_active = set()


async def _handle(symbol):
    try:
        if symbol in _active:
            logger.info(f"{symbol} already has an active trade, skipping")
            return
        _active.add(symbol)

        if not await validate(symbol):
            logger.info(f"{symbol} failed validation")
            return

        cap = await classify(symbol)
        tp = get_tp(cap)
        logger.info(f"{symbol} classified={cap} tp={tp}%")

        entry, qty = await open_trade(symbol)
        if entry is None or qty is None or qty <= 0:
            logger.error(f"{symbol} open_trade returned invalid entry/qty")
            return

        await manage(symbol, entry, qty, tp)
    except Exception as e:
        logger.exception(f"Error handling signal {symbol}: {e}")
    finally:
        _active.discard(symbol)


async def start_router():
    pubsub = await subscribe("signals")

    async for msg in pubsub.listen():
        if msg["type"] != "message":
            continue

        try:
            data = json.loads(msg["data"])
            symbol = data["symbol"]
        except Exception as e:
            logger.error(f"Bad signal payload: {e}")
            continue

        asyncio.create_task(_handle(symbol))
