import os
from dotenv import load_dotenv

load_dotenv()

class Config:

    TG_API_ID = int(os.getenv("TG_API_ID"))
    TG_API_HASH = os.getenv("TG_API_HASH")
    TG_SESSION = os.getenv("TG_SESSION")
    CHANNELS = [c.strip() for c in os.getenv("TG_CHANNELS", "").split(",") if c.strip()]

    API_KEY = os.getenv("BINANCE_API_KEY")
    API_SECRET = os.getenv("BINANCE_SECRET")

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

    LOW_CAP_TP = float(os.getenv("LOW_CAP_TP"))
    MID_CAP_TP = float(os.getenv("MID_CAP_TP"))
    BIG_CAP_TP = float(os.getenv("BIG_CAP_TP"))

    LOW_CAP_SIZE_MAX = float(os.getenv("LOW_CAP_SIZE_MAX"))
    MID_CAP_SIZE_MAX = float(os.getenv("MID_CAP_SIZE_MAX"))

    STOP_LOSS = float(os.getenv("STOP_LOSS"))
    TRADE_SIZE = float(os.getenv("TRADE_USDT_SIZE"))

    ENABLE_ANTI_SCAM = os.getenv("ENABLE_ANTI_SCAM", "false").lower() == "true"

    COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
    MARKETCAP_UPDATE_HOURS = float(os.getenv("MARKETCAP_UPDATE_HOURS", "4"))
    MARKETCAP_MAX_PAGES = int(os.getenv("MARKETCAP_MAX_PAGES", "20"))
