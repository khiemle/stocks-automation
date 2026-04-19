"""Integration tests for TradingBot lifecycle (Week 6)."""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from core.protocols import OrderResult, SignalResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    close = np.linspace(50_000.0, 55_000.0, n)
    high = close * 1.002
    low = close * 0.998
    vol = np.full(n, 600_000.0)
    vol[-3:] = 1_500_000.0
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": vol}, index=idx)


def _make_bot(tmp_path: Path, config_overrides: dict | None = None):
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    bot_module._SIGNAL_QUEUE_PATH = tmp_path / "state" / "signal_queue.json"
    pm_module._DEFAULT_DB_PATH = tmp_path / "data" / "trades.db"
    pm_module._DEFAULT_PORTFOLIO_PATH = tmp_path / "data" / "portfolio.json"

    from core.bot import TradingBot

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal_engines": [{"name": "MomentumV1", "enabled": True, "weight": 1.0}],
        "signal": {"min_score": 0.55},
        "scheduler": {
            "daily_scan_time": "15:35",
            "order_placement_time": "09:10",
            "cancel_unfilled_time": "14:30",
            "equity_snapshot_time": "15:10",
            "weekly_reset_day": "monday",
            "weekly_reset_time": "08:00",
            "signal_expiry_time": "08:30",
            "intraday_interval_minutes": 30,
        },
        "telegram": {"enabled": False},
        "watchlist": [],
        "mode": "PAPER",
    }
    if config_overrides:
        config.update(config_overrides)

    dm = MagicMock()
    dm.get_universe.return_value = ["VCB", "HPG"]
    dm.get_ohlcv.return_value = _make_ohlcv()

    broker = MagicMock()
    broker.get_order_status.side_effect = Exception("no orders")
    broker.place_order.return_value = OrderResult("ord-001", "SIMULATED", "ok")
    broker.cancel_order.return_value = True

    engine = MagicMock()
    engine.name = "MomentumV1"
    engine.is_eligible.return_value = (True, "")
    engine.evaluate.return_value = SignalResult(
        score=0.70, regime="TRENDING", action="BUY", confidence=0.85,
        indicators={"close": 55_000, "atr": 1_000, "ema20": 54_000, "ema60": 52_000,
                    "ema200": 50_000, "macd": 100, "macd_signal": 80,
                    "rsi": 62, "adx": 30, "adx_pos": 28, "adx_neg": 15,
                    "vol_ma20": 600_000, "vol_ratio": 2.5},
    )

    bot = TradingBot(config=config, data_manager=dm, signal_engines=[engine], broker=broker)
    return bot, dm, broker, engine


# ---------------------------------------------------------------------------
# test_full_daily_scan_cycle
# ---------------------------------------------------------------------------

def test_full_daily_scan_cycle(tmp_path):
    """Trigger daily scan → signal_queue.json được tạo với PENDING signals."""
    bot, dm, broker, engine = _make_bot(tmp_path)

    import core.bot as bot_module
    from unittest.mock import patch

    with patch("core.bot.MarketRegime") as mock_regime:
        mock_regime.return_value.context.return_value = {"macro_above_ema50": True}
        bot.daily_scan_job()

    queue_path = bot_module._SIGNAL_QUEUE_PATH
    assert queue_path.exists(), "signal_queue.json phải được tạo"
    signals = json.loads(queue_path.read_text())
    assert len(signals) >= 1, "Phải có ít nhất 1 PENDING signal"
    assert all(s["status"] == "PENDING" for s in signals)
    assert all(s["action"] == "BUY" for s in signals)
    # Both VCB and HPG should appear
    syms = {s["symbol"] for s in signals}
    assert syms == {"VCB", "HPG"}


# ---------------------------------------------------------------------------
# test_order_placement_after_approve
# ---------------------------------------------------------------------------

def test_order_placement_after_approve(tmp_path):
    """Approve signal → order_placement_job → broker.place_order called."""
    bot, dm, broker, engine = _make_bot(tmp_path)

    import core.bot as bot_module
    from unittest.mock import patch

    # Run scan to generate signals
    with patch("core.bot.MarketRegime") as mock_regime:
        mock_regime.return_value.context.return_value = {"macro_above_ema50": True}
        bot.daily_scan_job()

    # Approve the first signal (simulates streamlit UI approval)
    assert len(bot.queue) > 0
    first_sig = bot.queue[0]
    first_sig.status = "APPROVED"
    bot._save_queue()

    # Run order placement
    bot.order_placement_job()

    assert broker.place_order.call_count == 1
    placed_signal = [s for s in bot.queue if s.symbol == first_sig.symbol][0]
    assert placed_signal.status == "ORDER_PLACED"


# ---------------------------------------------------------------------------
# test_bot_recovers_after_simulated_crash
# ---------------------------------------------------------------------------

def test_bot_recovers_after_simulated_crash(tmp_path):
    """Kill bot + restart → portfolio positions intact, no duplicate signals."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    from core.portfolio_manager import Position

    # Simulate pre-existing state from "before crash"
    queue_path = bot_module._SIGNAL_QUEUE_PATH
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps([
        {
            "id": "sig-pre-crash",
            "symbol": "VCB", "action": "BUY", "score": 0.70,
            "engine": "MomentumV1", "source": "EOD",
            "created_at": datetime.now().isoformat(),
            "stop_loss": 47_500, "take_profit": 54_500,
            "indicators": {}, "status": "PENDING",
        }
    ]))

    portfolio_path = pm_module._DEFAULT_PORTFOLIO_PATH
    portfolio_path.parent.mkdir(parents=True, exist_ok=True)
    portfolio_path.write_text(json.dumps({
        "cash": 460_000_000,
        "equity_week_start": 500_000_000,
        "week_start_date": date.today().isoformat(),
        "positions": {
            "HPG": {
                "symbol": "HPG", "qty": 2000, "avg_price": 40_000,
                "stop_loss": 38_000, "take_profit": 48_000,
                "buy_date": date.today().isoformat(),
                "engine": "MomentumV1",
                "entry_atr": 800, "trail_active": False,
            }
        },
    }))

    dm = MagicMock()
    dm.get_universe.return_value = []
    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()
    broker.place_order.return_value = OrderResult("ord-new", "SIMULATED", "ok")

    from core.bot import TradingBot
    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE", "broker": "SimulatedBroker",
        "signal_engines": [], "signal": {}, "scheduler": {},
        "telegram": {"enabled": False}, "watchlist": [], "mode": "PAPER",
    }
    bot = TradingBot(config=config, data_manager=dm, signal_engines=[], broker=broker)

    # Portfolio must survive crash
    assert "HPG" in bot.portfolio.positions
    assert bot.portfolio.cash == 460_000_000
    assert bot.portfolio.positions["HPG"].qty == 2000

    # Signal queue must be restored with no duplicates
    assert len(bot.queue) == 1
    assert bot.queue[0].symbol == "VCB"
    assert bot.queue[0].status == "PENDING"
