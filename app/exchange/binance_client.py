from binance import AsyncClient
from app.core.config import Config

_client: AsyncClient | None = None
_lock = None


async def get_client() -> AsyncClient:
    global _client, _lock
    if _client is None:
        import asyncio
        if _lock is None:
            _lock = asyncio.Lock()
        async with _lock:
            if _client is None:
                _client = await AsyncClient.create(Config.API_KEY, Config.API_SECRET)
    return _client


async def close_client():
    global _client
    if _client is not None:
        await _client.close_connection()
        _client = None
