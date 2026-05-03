from telethon import TelegramClient, events
from telethon.sessions import StringSession
from app.core.config import Config
from app.core.logger import logger
from app.exchange.account import get_available_usdt, get_open_position_symbols
from app.strategy import trade_history, signal_router


_client: TelegramClient | None = None


async def notify(text: str):
    """Push a message to all admin chats. Safe to call even if bot isn't running."""
    if _client is None or not Config.TG_BOT_ADMIN_IDS:
        return
    for admin_id in Config.TG_BOT_ADMIN_IDS:
        try:
            await _client.send_message(admin_id, text, parse_mode="markdown")
        except Exception as e:
            logger.warning(f"notify {admin_id} failed: {e}")


def notify_bg(text: str):
    """Fire-and-forget notify so trade flow never blocks on Telegram."""
    if _client is None:
        return
    import asyncio as _a
    try:
        _a.create_task(notify(text))
    except RuntimeError:
        pass


def _is_authorized(sender_id) -> bool:
    if not Config.TG_BOT_ADMIN_IDS:
        return True
    try:
        return int(sender_id) in Config.TG_BOT_ADMIN_IDS
    except Exception:
        return False


async def start_command_bot():
    global _client
    if not Config.TG_BOT_TOKEN:
        logger.info("TG_BOT_TOKEN not set — command bot disabled")
        return

    _client = TelegramClient(
        StringSession(),
        Config.TG_API_ID,
        Config.TG_API_HASH,
    )

    HELP_TEXT = (
        "🤖 *Sniper Bot — Commands*\n\n"
        "📊 *Monitoring*\n"
        "`/current` — Show the trade currently running (symbol, entry, qty, "
        "leverage, margin, TP target, open time). Replies _'No trade running'_ if idle.\n\n"
        "`/balance` — Live futures wallet balance, your initial balance, and "
        "total change since the bot started (USDT and %).\n\n"
        "`/report` — Full trade history: initial vs current balance, total PnL, "
        "win rate, plus the last 15 trades with balance before → after.\n\n"
        "`/status` — Bot health: trading slot busy/free, open Binance positions, "
        "channels being watched, sizing mode, leverage cap & ladder, SL mode.\n\n"
        "ℹ️ *Info*\n"
        "`/start` — Welcome screen.\n"
        "`/help` — This message.\n\n"
        "🔔 *Auto-notifications*\n"
        "You'll automatically get pinged for every trade event:\n"
        "• 🟢 Trade opened (with full details + latency)\n"
        "• 🎯 Take-profit hit\n"
        "• 🛑 Stop-loss hit\n"
        "• 🔒 Position closed (manual / liquidation)\n"
        "• ⏭️ Signal dropped (another trade in progress)\n"
        "• ⚠️ Validation failed / ❌ Open failed / 💥 Errors"
    )

    @_client.on(events.NewMessage(pattern=r"^/start"))
    async def _start(event):
        if not _is_authorized(event.sender_id):
            return
        await event.reply(HELP_TEXT, parse_mode="markdown")

    @_client.on(events.NewMessage(pattern=r"^/help"))
    async def _help(event):
        if not _is_authorized(event.sender_id):
            return
        await event.reply(HELP_TEXT, parse_mode="markdown")

    @_client.on(events.NewMessage(pattern=r"^/current"))
    async def _current(event):
        if not _is_authorized(event.sender_id):
            return
        cur = trade_history.get_current()
        if not cur:
            await event.reply("📭 No trade currently running.")
            return
        msg = (
            f"🟢 *Active Trade*\n"
            f"Symbol: `{cur['symbol']}`\n"
            f"Entry: `{cur['entry']}`\n"
            f"Qty: `{cur['qty']}`\n"
            f"Leverage: `{cur['leverage']}x`\n"
            f"Margin: `{cur['margin']:.2f}` USDT\n"
            f"TP target: `{cur['tp_pct']}%`\n"
            f"Opened: `{cur['opened_at']}`"
        )
        await event.reply(msg, parse_mode="markdown")

    @_client.on(events.NewMessage(pattern=r"^/balance"))
    async def _balance(event):
        if not _is_authorized(event.sender_id):
            return
        try:
            bal = await get_available_usdt(force_refresh=True)
            init = trade_history.get_initial_balance()
            diff = bal - init if init > 0 else 0
            pct = (diff / init * 100) if init > 0 else 0
            arrow = "📈" if diff >= 0 else "📉"
            msg = (
                f"💰 *Balance*\n"
                f"Available: `{bal:.2f}` USDT\n"
                f"Initial: `{init:.2f}` USDT\n"
                f"{arrow} Change: `{diff:+.2f}` USDT (`{pct:+.2f}%`)"
            )
            await event.reply(msg, parse_mode="markdown")
        except Exception as e:
            await event.reply(f"⚠️ Balance fetch failed: {e}")

    @_client.on(events.NewMessage(pattern=r"^/status"))
    async def _status(event):
        if not _is_authorized(event.sender_id):
            return
        cur = trade_history.get_current()
        try:
            open_syms = await get_open_position_symbols()
        except Exception:
            open_syms = []
        trading = signal_router.is_trading()
        msg = (
            f"🤖 *Bot Status*\n"
            f"Trading slot: {'BUSY' if trading else 'FREE'}\n"
            f"Current trade: `{cur['symbol'] if cur else 'none'}`\n"
            f"Open positions on Binance: `{open_syms or 'none'}`\n"
            f"Channels: `{Config.CHANNELS}`\n"
            f"Sizing: `{Config.SIZING_MODE}` "
            f"({Config.TRADE_MARGIN_PCT}% / {Config.TRADE_SIZE} USDT)\n"
            f"Leverage cap: `{Config.MAX_LEVERAGE_CAP}x`\n"
            f"Ladder: `{Config.LEVERAGE_LADDER}`\n"
            f"SL mode: `{Config.SL_MODE}`"
        )
        await event.reply(msg, parse_mode="markdown")

    @_client.on(events.NewMessage(pattern=r"^/report"))
    async def _report(event):
        if not _is_authorized(event.sender_id):
            return
        try:
            current_bal = await get_available_usdt(force_refresh=True)
        except Exception:
            current_bal = None
        s = trade_history.summary(current_bal)
        trades = trade_history.get_trades()

        header = (
            f"📊 *Trade Report*\n"
            f"Initial balance: `{s['initial_balance']:.2f}` USDT\n"
            f"Current balance: `{s['current_balance']:.2f}` USDT\n"
            f"Total PnL: `{s['total_pnl_usdt']:+.2f}` USDT (`{s['total_pnl_pct']:+.2f}%`)\n"
            f"Trades: `{s['total_trades']}` | Wins: `{s['wins']}` | "
            f"Losses: `{s['losses']}` | WinRate: `{s['win_rate']}%`\n"
        )

        if not trades:
            await event.reply(header + "\n_No trades yet._", parse_mode="markdown")
            return

        last = trades[-15:]
        lines = ["\n*Last trades:*"]
        for t in last:
            sign = "✅" if t.get("pnl_usdt", 0) > 0 else "❌"
            lines.append(
                f"{sign} `{t['symbol']}` "
                f"{t.get('result','?')} "
                f"`{t.get('balance_before',0):.2f} → {t.get('balance_after',0):.2f}` "
                f"(`{t.get('pnl_usdt',0):+.2f}`)"
            )
        body = "\n".join(lines)

        out = header + body
        if len(out) > 3900:
            out = out[:3900] + "\n…(truncated)"
        await event.reply(out, parse_mode="markdown")

    await _client.start(bot_token=Config.TG_BOT_TOKEN)
    me = await _client.get_me()
    logger.info(f"Command bot online as @{me.username}")
    await _client.run_until_disconnected()
