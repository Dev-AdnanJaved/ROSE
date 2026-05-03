from app.core.config import Config
from app.exchange import symbols


async def validate(symbol: str) -> bool:
    if not symbols.is_tradable(symbol):
        return False
    if not Config.ENABLE_ANTI_SCAM:
        return True
    return True
