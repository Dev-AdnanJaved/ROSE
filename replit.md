# Telegram → Binance Futures Sniper Bot

## Overview
Ultra-low-latency Python bot. Listens to Telegram channels for `#COIN BULLISH` signals, opens leveraged USDT-M futures longs on Binance with TP/SL bracket orders, and exits at TP via a reduceOnly LIMIT order (guaranteed-profit exit, no slippage).

End-to-end target: signal → entry placed in well under 1 second (typical 150–300 ms after warmup).

## Pipeline
1. Telethon receives a channel message.
2. Parser matches `#COIN BULLISH` (case-insensitive) and emits `{symbol: "COINUSDT"}`.
3. In-process `asyncio.Queue` (no Redis hop) delivers to the router.
4. Router runs `validate` + `classify` in parallel.
5. `executor.open_trade`:
   - sets max leverage (capped by `MAX_LEVERAGE_CAP`) and `ISOLATED` margin in parallel with the mark-price fetch,
   - aborts if leverage/margin setup fails,
   - sizes order = `TRADE_USDT_SIZE * leverage / mark_price`, rounded to LOT_SIZE,
   - sends MARKET BUY,
   - places reduceOnly LIMIT TP + reduceOnly STOP_MARKET SL **in parallel** via `asyncio.gather`.
6. `position_manager.watch` polls TP/SL order status; when one fills, cancels the sibling.

## Pre-warm at startup
`app.main._prewarm` runs once before listening:
- `symbols.warmup()` — single REST call each for `futures_exchange_info` + `futures_leverage_bracket`, populating filters, tick/step sizes, and max leverage for every USDT-M symbol. Bot exits if this fails.
- `fetch_marketcaps()` — parallelizes all 20 CoinGecko Pro pages via `asyncio.gather` (one call per page). Refreshed every 4 h.

## Modules
- `app/main.py` — pre-warm + run gateway, router, marketcap updater concurrently.
- `app/core/config.py` — env loader with safe defaults.
- `app/core/logger.py` — loguru, stderr + rotating `bot.log`.
- `app/bus/redis_bus.py` — in-process `asyncio.Queue` (filename kept for compat; no Redis used).
- `app/telegram/parser.py` — strict `#COIN BULLISH` regex.
- `app/gateway/telegram_gateway.py` — Telethon listener.
- `app/exchange/binance_client.py` — singleton `AsyncClient`.
- `app/exchange/symbols.py` — pre-warmed exchange-info + leverage cache, per-symbol leverage/margin "already set" flags, qty/price rounding.
- `app/exchange/executor.py` — leverage/margin setup, sizing, MARKET entry, parallel TP-LIMIT + SL-STOP.
- `app/strategy/signal_router.py` — async dispatcher with per-symbol dedupe.
- `app/strategy/validator.py` — symbol must exist on Binance USDT-M.
- `app/strategy/tp_selector.py` — TP% by cap tier.
- `app/strategy/position_manager.py` — fill-watch with sibling cancel.
- `app/market/coin_classifier.py` — LOW/MID/BIG buckets.
- `app/market/marketcap_cache.py` — JSON-backed cache, auto-loaded at import.
- `app/market/marketcap_updater.py` — parallel paginated CoinGecko fetch.

## Environment Variables
Required: `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`, `TG_CHANNELS`, `BINANCE_API_KEY`, `BINANCE_SECRET`, `COINGECKO_API_KEY`.
With defaults: `LOW_CAP_TP=5`, `MID_CAP_TP=3`, `BIG_CAP_TP=2`, `LOW_CAP_SIZE_MAX=5e8`, `MID_CAP_SIZE_MAX=5e9`, `STOP_LOSS=2`, `TRADE_USDT_SIZE=50`, `MAX_LEVERAGE_CAP=125`, `MARGIN_TYPE=ISOLATED`, `USE_LIMIT_TP=true`, `TP_LIMIT_OFFSET_BPS=0`, `ENABLE_ANTI_SCAM=false`, `MARKETCAP_UPDATE_HOURS=4`, `MARKETCAP_MAX_PAGES=20`.

Add the new keys to `.env`:
```
MAX_LEVERAGE_CAP=125
MARGIN_TYPE=ISOLATED
USE_LIMIT_TP=true
TP_LIMIT_OFFSET_BPS=0
```

## Run
`python run.py` — Redis is no longer needed. First run will create the Telethon session file.
