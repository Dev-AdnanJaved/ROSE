from app.exchange.binance_client import get_client
from app.core.config import Config
import asyncio

async def manage(symbol, entry, tp):

    client = await get_client()

    while True:

        price = float(
            (await client.futures_mark_price(symbol=symbol))["markPrice"]
        )

        pnl = (price-entry)/entry*100

        if pnl >= tp or pnl <= -Config.STOP_LOSS:

            await client.futures_create_order(
                symbol=symbol,
                side="SELL",
                type="MARKET",
                quantity=0.01
            )
            break

        await asyncio.sleep(0.3)