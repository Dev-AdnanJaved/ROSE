import aiohttp
import asyncio
from app.market.marketcap_cache import update_cache
from app.core.config import Config

URL = "https://pro-api.coingecko.com/api/v3/coins/markets"

async def fetch_marketcaps():

    params = {
        "vs_currency": "usd",
        "per_page": 250,
        "page": 1
    }

    headers = {
        "x-cg-pro-api-key": Config.COINGECKO_API_KEY
    }

    all_caps = {}

    async with aiohttp.ClientSession() as session:

        while True:

            async with session.get(URL, params=params, headers=headers) as r:
                data = await r.json()

            if not data:
                break

            for coin in data:
                all_caps[coin["symbol"].lower()] = coin["market_cap"]

            params["page"] += 1

    update_cache(all_caps)

    print("✅ Market caps updated")
    
    
async def start_marketcap_updater():

    while True:

        try:
            await fetch_marketcaps()
        except Exception as e:
            print("MarketCap update error:", e)

        await asyncio.sleep(Config.MARKETCAP_UPDATE_HOURS * 3600)    
    
    