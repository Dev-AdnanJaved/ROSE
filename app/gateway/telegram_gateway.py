from telethon import TelegramClient, events
from telethon.sessions import StringSession
from app.core.config import Config
from app.telegram.parser import parse_signal
from app.bus.redis_bus import publish
from app.core.logger import logger


def _build_session():
    """If TG_SESSION looks like a session string (long), use StringSession.
    Otherwise treat it as a SQLite session filename."""
    s = Config.TG_SESSION or "sniper"
    if len(s) > 50:
        return StringSession(s)
    return s


client = TelegramClient(
    _build_session(),
    Config.TG_API_ID,
    Config.TG_API_HASH,
)


async def start_telegram():

    @client.on(events.NewMessage(chats=Config.CHANNELS))
    async def handler(event):
        try:
            symbol = parse_signal(event.raw_text)
            if symbol:
                await publish({"symbol": symbol})
        except Exception as e:
            logger.exception(f"telegram handler error: {e}")

    await client.start()
    logger.info(f"Telegram listening on: {Config.CHANNELS}")
    await client.run_until_disconnected()
