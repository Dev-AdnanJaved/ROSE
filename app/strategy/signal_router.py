import json
from app.bus.redis_bus import subscribe
from app.strategy.validator import validate
from app.market.coin_classifier import classify
from app.strategy.tp_selector import get_tp
from app.exchange.executor import open_trade
from app.strategy.position_manager import manage

async def start_router():

    pubsub = await subscribe("signals")

    async for msg in pubsub.listen():

        if msg["type"] != "message":
            continue

        data = json.loads(msg["data"])
        symbol = data["symbol"]

        if not await validate(symbol):
            continue

        cap = await classify(symbol)
        tp = get_tp(cap)

        entry = await open_trade(symbol)

        await manage(symbol, entry, tp)