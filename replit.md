# Telegram → Binance Futures Sniper Bot

## Overview
A Python async bot that listens to Telegram channels for trading signals, parses coin symbols, classifies them by market cap, opens market BUY orders on Binance USDT-M Futures, and manages each position to TP or SL.

## Architecture
- **Entry**: `run.py` → `app/main.py` runs three concurrent coroutines:
  - `start_telegram` — Telethon client listening on configured channels.
  - `start_router` — Redis pubsub consumer that handles each signal as a background task.
  - `start_marketcap_updater` — periodic CoinGecko Pro fetch.
- **Bus**: Redis pub/sub channel `signals` decouples ingestion from execution.
- **Market data**: market caps cached in `marketcap_cache.json` and refreshed every `MARKETCAP_UPDATE_HOURS`.
- **Trading**: `executor.open_trade` validates the symbol against Binance futures `exchangeInfo`, sizes the order from `TRADE_USDT_SIZE / markPrice` rounded to LOT_SIZE step. `position_manager.manage` polls mark price and closes with `reduceOnly` on TP/SL with retry/backoff.

## Modules
- `app/core/config.py` — env loader. All env vars required by the codebase.
- `app/core/logger.py` — loguru, stderr + rotating `bot.log`.
- `app/telegram/parser.py` — requires a signal keyword (BUY/LONG/ENTRY/SIGNAL/SNIPE/CALL) plus a 2–10 letter symbol; common words blacklisted.
- `app/gateway/telegram_gateway.py` — Telethon listener.
- `app/bus/redis_bus.py` — async Redis pub/sub.
- `app/strategy/signal_router.py` — async dispatcher; deduplicates concurrent trades on the same symbol.
- `app/strategy/validator.py` — anti-scam hook (extensible).
- `app/strategy/tp_selector.py` — TP% by cap tier.
- `app/strategy/position_manager.py` — TP/SL monitor with retrying close.
- `app/exchange/binance_client.py` — singleton `AsyncClient`.
- `app/exchange/executor.py` — symbol validation, sizing, market BUY.
- `app/market/coin_classifier.py` — LOW/MID/BIG by `LOW_CAP_SIZE_MAX` / `MID_CAP_SIZE_MAX`.
- `app/market/marketcap_cache.py` — JSON-backed cache, auto-loaded at import.
- `app/market/marketcap_updater.py` — paginated CoinGecko Pro fetch with page cap.

## Environment Variables (`.env`)
TG_API_ID, TG_API_HASH, TG_SESSION, TG_CHANNELS,
BINANCE_API_KEY, BINANCE_SECRET,
REDIS_HOST, REDIS_PORT,
LOW_CAP_TP, MID_CAP_TP, BIG_CAP_TP,
LOW_CAP_SIZE_MAX, MID_CAP_SIZE_MAX,
STOP_LOSS, TRADE_USDT_SIZE,
ENABLE_ANTI_SCAM,
COINGECKO_API_KEY, MARKETCAP_UPDATE_HOURS, MARKETCAP_MAX_PAGES.

## Run
`python run.py` (requires a running Redis on `REDIS_HOST:REDIS_PORT`).
