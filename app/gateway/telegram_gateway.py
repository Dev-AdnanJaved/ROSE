from telethon import TelegramClient, events
from app.core.config import Config
from app.telegram.parser import parse_signal
from app.bus.redis_bus import publish

client = TelegramClient(
    Config.TG_SESSION,
    Config.TG_API_ID,
    Config.TG_API_HASH
)

async def start_telegram():

    @client.on(events.NewMessage(chats=Config.CHANNELS))
    async def handler(event):

        symbol = parse_signal(event.raw_text)

        if symbol:
            await publish("signals", {"symbol": symbol})

    await client.start()
    await client.run_until_disconnected()