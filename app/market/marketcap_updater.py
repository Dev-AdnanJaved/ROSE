import aiohttp
import asyncio
from app.market.marketcap_cache import update_cache, marketcaps
from app.core.config import Config
from app.core.logger import logger

PRO_URL = "https://pro-api.coingecko.com/api/v3/coins/markets"
FREE_URL = "https://api.coingecko.com/api/v3/coins/markets"


def _key_info():
    """Returns (url, headers, mode_name). Auto-detects pro vs demo (free) key."""
    k = (Config.COINGECKO_API_KEY or "").strip()
    if not k or k.lower() in ("your_key_here", "none", "null"):
        return FREE_URL, {}, "public"
    # CoinGecko free/demo keys start with 'CG-'. Pro keys do not.
    if k.startswith("CG-"):
        return FREE_URL, {"x-cg-demo-api-key": k}, "demo"
    return PRO_URL, {"x-cg-pro-api-key": k}, "pro"


async def _fetch_page(session, page, url, headers):
    params = {"vs_currency": "usd", "per_page": 250, "page": page}
    try:
        async with session.get(url, params=params, headers=headers, timeout=30) as r:
            if r.status == 429:
                logger.warning(f"CoinGecko page {page} rate-limited (429)")
                return None
            if r.status != 200:
                logger.error(f"CoinGecko page {page} -> HTTP {r.status}")
                return None
            return await r.json()
    except Exception as e:
        logger.warning(f"CoinGecko page {page} fetch error: {e}")
        return None


async def fetch_marketcaps():
    url, headers, mode = _key_info()
    using_free = mode in ("public", "demo")
    # Free endpoint is rate-limited (~10-30 req/min). Cap pages and serialize.
    max_pages = min(Config.MARKETCAP_MAX_PAGES, 4) if using_free else Config.MARKETCAP_MAX_PAGES

    logger.info(
        f"CoinGecko: mode={mode} url={url} pages={max_pages} "
        f"{'(serialized)' if using_free else '(parallel)'}"
    )

    all_caps: dict[str, float] = {}
    async with aiohttp.ClientSession() as session:
        if using_free:
            results = []
            for p in range(1, max_pages + 1):
                results.append(await _fetch_page(session, p, url, headers))
                await asyncio.sleep(2.0)
        else:
            results = await asyncio.gather(
                *[_fetch_page(session, p, url, headers) for p in range(1, max_pages + 1)],
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
