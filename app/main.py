import asyncio
from app.gateway.telegram_gateway import start_telegram
from app.strategy.signal_router import start_router
from app.market.marketcap_updater import start_marketcap_updater

async def start():
    await asyncio.gather(
        start_telegram(),
        start_router(),
        start_marketcap_updater()
    )