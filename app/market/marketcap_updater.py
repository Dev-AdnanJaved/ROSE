import aiohttp
import asyncio
from app.market.marketcap_cache import update_cache
from app.core.config import Config
from app.core.logger import logger

URL = "https://pro-api.coingecko.com/api/v3/coins/markets"


async def fetch_marketcaps():
    headers = {"x-cg-pro-api-key": Config.COINGECKO_API_KEY}
    all_caps = {}

    async with aiohttp.ClientSession() as session:
        for page in range(1, Config.MARKETCAP_MAX_PAGES + 1):
            params = {
                "vs_currency": "usd",
                "per_page": 250,
                "page": page,
            }
            async with session.get(URL, params=params, headers=headers) as r:
                if r.status != 200:
                    logger.error(f"CoinGecko returned {r.status}")
                    break
                data = await r.json()

            if not data:
                break

            for coin in data:
                sym = coin.get("symbol", "").lower()
                cap = coin.get("market_cap")
                if sym and cap is not None:
                    all_caps[sym] = cap

            if len(data) < 250:
                break

    if all_caps:
        update_cache(all_caps)
        logger.info(f"Market caps updated ({len(all_caps)} coins)")
    else:
        logger.warning("Market cap fetch returned no data")


async def start_marketcap_updater():
    while True:
        try:
            await fetch_marketcaps()
        except Exception as e:
            logger.exception(f"MarketCap update error: {e}")

        await asyncio.sleep(Config.MARKETCAP_UPDATE_HOURS * 3600)
