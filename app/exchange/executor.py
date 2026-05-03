from app.exchange.binance_client import get_client

async def open_trade(symbol):

    client = await get_client()

    order = await client.futures_create_order(
        symbol=symbol,
        side="BUY",
        type="MARKET",
        quantity=0.01
    )

    return float(order["avgPrice"])