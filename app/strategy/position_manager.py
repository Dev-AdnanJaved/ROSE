from app.exchange.binance_client import get_client
from app.core.config import Config
from app.core.logger import logger
import asyncio


async def _close_position(client, symbol, qty):
    delay = 1.0
    for attempt in range(1, 8):
        try:
            await client.futures_create_order(
                symbol=symbol,
                side="SELL",
                type="MARKET",
                quantity=qty,
                reduceOnly=True,
            )
            return True
        except Exception as e:
            logger.exception(
                f"{symbol} close attempt {attempt} failed: {e}"
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
    logger.error(f"{symbol} FAILED TO CLOSE after retries — manual intervention required")
    return False


async def manage(symbol, entry, qty, tp):
    client = await get_client()

    while True:
        try:
            price = float(
                (await client.futures_mark_price(symbol=symbol))["markPrice"]
            )
        except Exception as e:
            logger.error(f"{symbol} mark price fetch failed: {e}")
            await asyncio.sleep(1)
            continue

        pnl = (price - entry) / entry * 100

        if pnl >= tp or pnl <= -Config.STOP_LOSS:
            reason = "TP" if pnl >= tp else "SL"
            logger.info(f"{symbol} hit {reason} pnl={pnl:.2f}% — closing")
            ok = await _close_position(client, symbol, qty)
            if ok:
                logger.info(f"CLOSED {symbol} {reason} pnl={pnl:.2f}% qty={qty}")
            return

        await asyncio.sleep(0.3)
