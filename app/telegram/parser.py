import re
from app.core.logger import logger

SIGNAL_RE = re.compile(
    r"#([A-Z0-9]{2,15})\s+BULLISH\b",
    re.IGNORECASE,
)


def parse_signal(text: str):
    if not text:
        return None
    m = SIGNAL_RE.search(text)
    if not m:
        return None
    coin = m.group(1).upper()
    if coin in ("USDT", "USD", "BUSD"):
        return None
    symbol = coin + "USDT"
    logger.info(f"Parsed BULLISH signal: {symbol}")
    return symbol
