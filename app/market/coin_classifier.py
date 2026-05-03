from app.market.marketcap_cache import get_marketcap
from app.core.config import Config


async def classify(symbol: str) -> str:
    cap = get_marketcap(symbol)
    if not cap:
        return "MID"
    if cap < Config.LOW_CAP_SIZE_MAX:
        return "LOW"
    if cap < Config.MID_CAP_SIZE_MAX:
        return "MID"
    return "BIG"
