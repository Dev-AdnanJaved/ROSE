import os
from dotenv import load_dotenv

load_dotenv()


def _f(name, default=None):
    v = os.getenv(name)
    return float(v) if v not in (None, "") else default


def _i(name, default=None):
    v = os.getenv(name)
    return int(v) if v not in (None, "") else default


def _b(name, default=False):
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("true", "1", "yes", "y", "on")


class Config:

    TG_API_ID = _i("TG_API_ID")
    TG_API_HASH = os.getenv("TG_API_HASH")
    TG_SESSION = os.getenv("TG_SESSION", "sniper")
    CHANNELS = [c.strip() for c in os.getenv("TG_CHANNELS", "").split(",") if c.strip()]

    API_KEY = os.getenv("BINANCE_API_KEY")
    API_SECRET = os.getenv("BINANCE_SECRET")

    LOW_CAP_TP = _f("LOW_CAP_TP", 5.0)
    MID_CAP_TP = _f("MID_CAP_TP", 3.0)
    BIG_CAP_TP = _f("BIG_CAP_TP", 2.0)

    LOW_CAP_SIZE_MAX = _f("LOW_CAP_SIZE_MAX", 500_000_000)
    MID_CAP_SIZE_MAX = _f("MID_CAP_SIZE_MAX", 5_000_000_000)

    STOP_LOSS = _f("STOP_LOSS", 2.0)
    TRADE_SIZE = _f("TRADE_USDT_SIZE", 50.0)
    TRADE_MARGIN_PCT = _f("TRADE_MARGIN_PCT", 10.0)
    SIZING_MODE = os.getenv("SIZING_MODE", "PERCENT").upper()
    BALANCE_CACHE_SECONDS = _f("BALANCE_CACHE_SECONDS", 30.0)

    MAX_LEVERAGE_CAP = _i("MAX_LEVERAGE_CAP", 50)
    LEVERAGE_LADDER = [
        int(x) for x in os.getenv("LEVERAGE_LADDER", "50,40,30,20,10,5").split(",")
        if x.strip()
    ]
    MARGIN_TYPE = os.getenv("MARGIN_TYPE", "ISOLATED").upper()

    USE_LIMIT_TP = _b("USE_LIMIT_TP", True)
    TP_LIMIT_OFFSET_BPS = _f("TP_LIMIT_OFFSET_BPS", 0.0)

    SL_MODE = os.getenv("SL_MODE", "LIQUIDATION").upper()
    SL_LIQUIDATION_BUFFER_PCT = _f("SL_LIQUIDATION_BUFFER_PCT", 0.5)

    ENABLE_ANTI_SCAM = _b("ENABLE_ANTI_SCAM", False)

    COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
    MARKETCAP_UPDATE_HOURS = _f("MARKETCAP_UPDATE_HOURS", 4.0)
    MARKETCAP_MAX_PAGES = _i("MARKETCAP_MAX_PAGES", 20)
