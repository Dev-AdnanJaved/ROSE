from binance import AsyncClient
from app.core.config import Config

client = None

async def get_client():
    global client
    if client is None:
        client = await AsyncClient.create(
            Config.API_KEY,
            Config.API_SECRET
        )
    return client