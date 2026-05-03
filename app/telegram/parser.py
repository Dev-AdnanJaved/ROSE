import re
from app.core.logger import logger

SIGNAL_KEYWORDS = re.compile(
    r"\b(BUY|LONG|ENTRY|SIGNAL|SNIPE|CALL)\b",
    re.IGNORECASE,
)

SYMBOL_PATTERN = re.compile(
    r"(?:#|\$|\b)([A-Z]{2,10})(?:/?USDT|/?USD|\b)"
)

BLACKLIST = {
    "BUY", "SELL", "LONG", "SHORT", "ENTRY", "EXIT", "TP", "SL",
    "USD", "USDT", "BTC", "ETH",
    "STOP", "LOSS", "TARGET", "SIGNAL", "CALL", "SNIPE",
    "NOW", "FAST", "PUMP", "DUMP", "MOON", "HOLD", "DCA",
    "THE", "AND", "FOR", "GET", "ALL", "OUT", "NEW", "BIG", "OK",
}


def parse_signal(text):
    if not text:
        return None

    if not SIGNAL_KEYWORDS.search(text):
        return None

    upper = text.upper()

    for match in SYMBOL_PATTERN.finditer(upper):
        symbol = match.group(1)
        if symbol in BLACKLIST:
            continue
        logger.info(f"Parsed signal symbol: {symbol}")
        return symbol + "USDT"

    return None
