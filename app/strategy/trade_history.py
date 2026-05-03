import json
import os
import time
import asyncio
from datetime import datetime, timezone
from app.core.logger import logger

HISTORY_FILE = os.getenv("TRADE_HISTORY_FILE", "trade_history.json")

_state = {
    "initial_balance": 0.0,
    "initial_balance_ts": 0.0,
    "trades": [],
    "current": None,
}
_lock = asyncio.Lock()


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


async def _persist():
    try:
        tmp = HISTORY_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_state, f, indent=2, default=str)
        os.replace(tmp, HISTORY_FILE)
    except Exception as e:
        logger.warning(f"trade_history persist failed: {e}")


def load():
    if not os.path.exists(HISTORY_FILE):
        return
    try:
        with open(HISTORY_FILE) as f:
            data = json.load(f)
        _state["initial_balance"] = float(data.get("initial_balance", 0))
        _state["initial_balance_ts"] = float(data.get("initial_balance_ts", 0))
        _state["trades"] = data.get("trades", [])
        _state["current"] = data.get("current")
        if _state["current"]:
            logger.info(f"Loaded incomplete trade from history: {_state['current'].get('symbol')}")
    except Exception as e:
        logger.warning(f"trade_history load failed: {e}")


async def set_initial_balance(balance: float):
    if _state["initial_balance"] > 0:
        return
    _state["initial_balance"] = balance
    _state["initial_balance_ts"] = time.time()
    async with _lock:
        await _persist()
    logger.info(f"Initial balance recorded: {balance:.2f} USDT")


async def trade_opened(symbol: str, entry: float, qty: float, leverage: int,
                       margin: float, balance_before: float, tp_pct: float):
    async with _lock:
        _state["current"] = {
            "symbol": symbol,
            "entry": entry,
            "qty": qty,
            "leverage": leverage,
            "margin": margin,
            "tp_pct": tp_pct,
            "balance_before": balance_before,
            "opened_at": _now_iso(),
            "opened_ts": time.time(),
        }
        await _persist()


async def trade_closed(result: str, balance_after: float, exit_price: float = None):
    async with _lock:
        cur = _state.get("current")
        if not cur:
            return
        pnl = balance_after - cur.get("balance_before", balance_after)
        pct = (pnl / cur["balance_before"] * 100) if cur.get("balance_before") else 0.0
        record = {
            **cur,
            "result": result,
            "exit_price": exit_price,
            "balance_after": balance_after,
            "pnl_usdt": round(pnl, 4),
            "pnl_pct_of_balance": round(pct, 3),
            "closed_at": _now_iso(),
            "duration_sec": round(time.time() - cur.get("opened_ts", time.time()), 1),
        }
        _state["trades"].append(record)
        _state["current"] = None
        await _persist()


def get_current() -> dict | None:
    return _state.get("current")


def get_initial_balance() -> float:
    return _state.get("initial_balance", 0.0)


def get_trades() -> list:
    return list(_state.get("trades", []))


def summary(current_balance: float = None) -> dict:
    trades = _state["trades"]
    wins = [t for t in trades if t.get("pnl_usdt", 0) > 0]
    losses = [t for t in trades if t.get("pnl_usdt", 0) <= 0]
    total_pnl = sum(t.get("pnl_usdt", 0) for t in trades)
    init = _state["initial_balance"]
    final = current_balance if current_balance is not None else (
        trades[-1]["balance_after"] if trades else init
    )
    return {
        "initial_balance": init,
        "current_balance": final,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "total_pnl_usdt": round(total_pnl, 4),
        "total_pnl_pct": round((final - init) / init * 100, 2) if init > 0 else 0,
    }
