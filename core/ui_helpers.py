"""
ui_helpers.py — Pure functions for Streamlit UI interactions.
All functions are side-effect-free w.r.t. broker/data — they only read/write
the shared JSON files (signal_queue.json, config.json).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path("config/config.json")
_SIGNAL_QUEUE_PATH = Path("state/signal_queue.json")
_DB_PATH = Path("data/trades.db")
_PORTFOLIO_PATH = Path("data/portfolio.json")
_EQUITY_HISTORY_PATH = Path("data/equity_history.csv")

_WATCHLIST_MAX = 10


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(path: Path = _CONFIG_PATH) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_config(config: dict, path: Path = _CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Signal queue helpers
# ---------------------------------------------------------------------------

def load_queue(path: Path = _SIGNAL_QUEUE_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def save_queue(signals: list[dict], path: Path = _SIGNAL_QUEUE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(signals, indent=2, ensure_ascii=False))


def approve_signal(signal_id: str, path: Path = _SIGNAL_QUEUE_PATH) -> bool:
    signals = load_queue(path)
    for s in signals:
        if s["id"] == signal_id and s["status"] == "PENDING":
            s["status"] = "APPROVED"
            save_queue(signals, path)
            return True
    return False


def reject_signal(signal_id: str, path: Path = _SIGNAL_QUEUE_PATH) -> bool:
    signals = load_queue(path)
    for s in signals:
        if s["id"] == signal_id and s["status"] == "PENDING":
            s["status"] = "REJECTED"
            save_queue(signals, path)
            return True
    return False


# ---------------------------------------------------------------------------
# Watchlist helpers
# ---------------------------------------------------------------------------

def add_to_watchlist(symbol: str, config_path: Path = _CONFIG_PATH) -> None:
    config = load_config(config_path)
    watchlist: list[str] = config.get("watchlist", [])
    if len(watchlist) >= _WATCHLIST_MAX:
        raise ValueError(f"Watchlist is full ({_WATCHLIST_MAX} max). Remove a symbol first.")
    symbol = symbol.upper().strip()
    if symbol and symbol not in watchlist:
        watchlist.append(symbol)
        config["watchlist"] = watchlist
        save_config(config, config_path)


def remove_from_watchlist(symbol: str, config_path: Path = _CONFIG_PATH) -> None:
    config = load_config(config_path)
    watchlist: list[str] = config.get("watchlist", [])
    symbol = symbol.upper().strip()
    if symbol in watchlist:
        watchlist.remove(symbol)
        config["watchlist"] = watchlist
        save_config(config, config_path)


# ---------------------------------------------------------------------------
# Portfolio / DB readers (read-only)
# ---------------------------------------------------------------------------

def load_portfolio(path: Path = _PORTFOLIO_PATH) -> dict:
    if not path.exists():
        return {"cash": 0, "positions": {}}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"cash": 0, "positions": {}}


def load_trades(db_path: Path = _DB_PATH) -> list[dict]:
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT symbol, side, quantity, entry_price, exit_price, "
                "entry_date, exit_date, gross_pnl, commission, slippage, "
                "net_pnl, engine, closed_at FROM trades ORDER BY closed_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def load_equity_history(db_path: Path = _DB_PATH) -> list[dict]:
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT recorded_date, cash, market_value, nav "
                "FROM equity_history ORDER BY recorded_date ASC"
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def compute_summary_metrics(trades: list[dict]) -> dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "total_net_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
        }
    wins = [t["net_pnl"] for t in trades if t["net_pnl"] > 0]
    losses = [t["net_pnl"] for t in trades if t["net_pnl"] < 0]
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    return {
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades) if trades else 0.0,
        "profit_factor": gross_wins / gross_losses if gross_losses > 0 else float("inf"),
        "total_net_pnl": sum(t["net_pnl"] for t in trades),
        "avg_win": gross_wins / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
    }
