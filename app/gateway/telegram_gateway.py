from telethon import TelegramClient, events
from app.core.config import Config
from app.telegram.parser import parse_signal
from app.bus.redis_bus import publish
from app.core.logger import logger

client = TelegramClient(
    Config.TG_SESSION,
    Config.TG_API_ID,
    Config.TG_API_HASH,
)


async def start_telegram():

    @client.on(events.NewMessage(chats=Config.CHANNELS))
    async def handler(event):
        try:
            symbol = parse_signal(event.raw_text)
            if symbol:
                logger.info(f"Signal detected: {symbol}")
                await publish("signals", {"symbol": symbol})
        except Exception as e:
            logger.exception(f"Telegram handler error: {e}")

    await client.start()
    logger.info(f"Telegram listening on channels: {Config.CHANNELS}")
    await client.run_until_disconnected()
