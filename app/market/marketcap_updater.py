import aiohttp
import asyncio
from app.market.marketcap_cache import update_cache, marketcaps
from app.core.config import Config
from app.core.logger import logger

URL = "https://pro-api.coingecko.com/api/v3/coins/markets"


async def _fetch_page(session, page):
    params = {"vs_currency": "usd", "per_page": 250, "page": page}
    headers = {"x-cg-pro-api-key": Config.COINGECKO_API_KEY} if Config.COINGECKO_API_KEY else {}
    async with session.get(URL, params=params, headers=headers, timeout=30) as r:
        if r.status != 200:
            logger.error(f"CoinGecko page {page} -> HTTP {r.status}")
            return None
        return await r.json()


async def fetch_marketcaps():
    if not Config.COINGECKO_API_KEY or Config.COINGECKO_API_KEY == "your_key_here":
        if not marketcaps:
            logger.warning("COINGECKO_API_KEY not set, skipping marketcap fetch")
        return

    all_caps: dict[str, float] = {}
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[_fetch_page(session, p) for p in range(1, Config.MARKETCAP_MAX_PAGES + 1)],
            return_exceptions=True,
        )

    for data in results:
        if not data or isinstance(data, Exception):
            continue
        for coin in data:
            sym = coin.get("symbol", "").lower()
            cap = coin.get("market_cap")
            if sym and cap is not None:
                all_caps[sym] = cap

    if all_caps:
        update_cache(all_caps)
        logger.info(f"Market caps updated ({len(all_caps)} coins)")
    else:
        logger.warning("Market cap fetch returned no data")


async def start_marketcap_updater():
    while True:
        await asyncio.sleep(Config.MARKETCAP_UPDATE_HOURS * 3600)
        try:
            await fetch_marketcaps()
        except Exception as e:
            logger.exception(f"MarketCap update error: {e}")
