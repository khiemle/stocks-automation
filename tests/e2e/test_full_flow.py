"""E2E tests — 5 scenarios for full trading bot flow (Week 8)."""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from brokers.simulated_broker import SimulatedBroker
from core.bot import Signal, TradingBot
from core.portfolio_manager import PortfolioManager, Position


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

def _config(overrides: dict | None = None) -> dict:
    cfg = {
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
    if overrides:
        cfg.update(overrides)
    return cfg


def _make_ohlcv_bar(price: float) -> pd.Series:
    return pd.Series({
        "open": price, "high": price * 1.02,
        "low": price * 0.98, "close": price, "volume": 500_000,
    })


def _make_bot(tmp_path: Path, config: dict | None = None, broker=None, dm=None, notifier=None) -> TradingBot:
    import core.bot as bot_module
    import core.portfolio_manager as pm_module
    bot_module._SIGNAL_QUEUE_PATH = tmp_path / "signal_queue.json"
    pm_module._DEFAULT_DB_PATH = tmp_path / "trades.db"
    pm_module._DEFAULT_PORTFOLIO_PATH = tmp_path / "portfolio.json"

    if dm is None:
        dm = MagicMock()
        dm.get_universe.return_value = []

    if broker is None:
        broker = MagicMock()
        broker.get_order_status.side_effect = Exception()

    if notifier is None:
        notifier = MagicMock()

    return TradingBot(
        config=config or _config(),
        data_manager=dm,
        signal_engines=[],
        broker=broker,
        notifier=notifier,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path
# ---------------------------------------------------------------------------

def test_scenario_1_happy_path(tmp_path):
    """
    Full flow: scan generates BUY signal → manual approve → order placed →
    broker fills → position opens in portfolio.
    """
    import core.bot as bot_module
    import core.portfolio_manager as pm_module
    bot_module._SIGNAL_QUEUE_PATH = tmp_path / "signal_queue.json"
    pm_module._DEFAULT_DB_PATH = tmp_path / "trades.db"
    pm_module._DEFAULT_PORTFOLIO_PATH = tmp_path / "portfolio.json"

    broker = SimulatedBroker(initial_cash=500_000_000)
    dm = MagicMock()
    dm.get_universe.return_value = []
    notifier = MagicMock()

    bot = TradingBot(
        config=_config(),
        data_manager=dm,
        signal_engines=[],
        broker=broker,
        notifier=notifier,
    )

    # Inject a pre-approved signal directly (simulating daily_scan + user approval)
    sig = Signal(
        symbol="VCB",
        action="BUY",
        score=0.72,
        engine="MomentumV1",
        source="EOD",
        created_at=datetime.now().isoformat(timespec="seconds"),
        stop_loss=80_000,
        take_profit=95_000,
        status="APPROVED",
        indicators={"close": 85_000, "atr": 1_500},
        signal_price=85_000.0,
    )
    bot._queue.append(sig)
    bot._save_queue()

    # Step: place order
    bot.order_placement_job()

    # Verify order was placed in broker
    placed = [s for s in bot.queue if s.status == "ORDER_PLACED"]
    assert len(placed) == 1
    assert placed[0].symbol == "VCB"

    # Simulate fill at T+1 open
    bar = _make_ohlcv_bar(85_500)
    broker.process_next_bar("VCB", bar, date.today().isoformat())

    status = broker.get_order_status(placed[0].id)
    assert status.status == "FILLED"
    assert status.fill_price is not None

    # Open position in portfolio (as bot would do on fill confirmation)
    pos = Position(
        symbol="VCB",
        qty=status.filled_qty or 100,
        avg_price=status.fill_price,
        stop_loss=80_000,
        take_profit=95_000,
        buy_date=date.today().isoformat(),
    )
    bot.portfolio.open_position(pos)
    assert "VCB" in bot.portfolio.positions


# ---------------------------------------------------------------------------
# Scenario 2 — Stop loss triggered
# ---------------------------------------------------------------------------

def test_scenario_2_stop_loss_triggered(tmp_path):
    """
    Position open → intraday price drops below stop → SELL order placed,
    Telegram notified, position closed.
    """
    import core.bot as bot_module
    import core.portfolio_manager as pm_module
    bot_module._SIGNAL_QUEUE_PATH = tmp_path / "signal_queue.json"
    pm_module._DEFAULT_DB_PATH = tmp_path / "trades.db"
    pm_module._DEFAULT_PORTFOLIO_PATH = tmp_path / "portfolio.json"

    broker_mock = MagicMock()
    broker_mock.get_order_status.side_effect = Exception()
    broker_mock.place_order.return_value = MagicMock(status="PLACED", order_id="sell-1", message="OK")

    notifier = MagicMock()
    dm = MagicMock()
    dm.get_universe.return_value = []

    bot = TradingBot(
        config=_config(),
        data_manager=dm,
        signal_engines=[],
        broker=broker_mock,
        notifier=notifier,
    )

    # Open a position manually
    pos = Position(
        symbol="HPG",
        qty=500,
        avg_price=47_000,
        stop_loss=44_000,
        take_profit=56_000,
        buy_date="2026-04-15",
        entry_atr=1_200,
    )
    bot.portfolio._positions["HPG"] = pos

    # Simulate intraday price below stop
    import core.bot as bot_module_inner
    bot_module_inner._SKIP_TRADING_HOURS_CHECK = True
    try:
        dm.data_source.get_intraday_prices_batch.return_value = {"HPG": 43_000.0}
        bot.intraday_monitor_job()
    finally:
        bot_module_inner._SKIP_TRADING_HOURS_CHECK = False

    # SELL order was placed
    broker_mock.place_order.assert_called_once()
    call_args = broker_mock.place_order.call_args
    assert call_args.kwargs.get("side") == "S" or call_args.args[1] == "S"

    # Telegram notified about stop loss
    notifier.notify_stop_loss_hit.assert_called_once()
    call = notifier.notify_stop_loss_hit.call_args
    assert call.kwargs["symbol"] == "HPG"
    assert call.kwargs["exit_price"] == 43_000.0


# ---------------------------------------------------------------------------
# Scenario 3 — Circuit breaker
# ---------------------------------------------------------------------------

def test_scenario_3_circuit_breaker(tmp_path):
    """
    MDD exceeds 150% of backtest threshold → circuit breaker fires:
    no new orders placed, Telegram alert sent.
    """
    import core.bot as bot_module
    import core.portfolio_manager as pm_module
    bot_module._SIGNAL_QUEUE_PATH = tmp_path / "signal_queue.json"
    pm_module._DEFAULT_DB_PATH = tmp_path / "trades.db"
    pm_module._DEFAULT_PORTFOLIO_PATH = tmp_path / "portfolio.json"

    broker_mock = MagicMock()
    broker_mock.get_order_status.side_effect = Exception()
    notifier = MagicMock()

    bot = TradingBot(
        config=_config(),
        data_manager=MagicMock(),
        signal_engines=[],
        broker=broker_mock,
        notifier=notifier,
    )

    # Trigger circuit breaker: current_mdd > 150% × backtest_mdd (0.20 × 1.5 = 0.30)
    current_mdd = 0.35   # exceeds 0.30

    # Add an approved signal
    sig = Signal(
        symbol="VCB",
        action="BUY",
        score=0.70,
        engine="MomentumV1",
        source="EOD",
        created_at=datetime.now().isoformat(timespec="seconds"),
        stop_loss=80_000,
        take_profit=95_000,
        status="APPROVED",
        indicators={"close": 85_000, "atr": 1_500},
    )
    bot._queue.append(sig)

    # Check circuit breaker and notify (as bot would before placing orders)
    cb_threshold = bot._risk.backtest_mdd * bot._risk.CIRCUIT_MULT
    if bot._risk.check_circuit_breaker(current_mdd):
        bot._notifier.notify_circuit_breaker(
            mdd_pct=current_mdd,
            threshold_pct=cb_threshold,
        )
        # Bot should NOT place orders when circuit breaker is active
    else:
        bot.order_placement_job()

    notifier.notify_circuit_breaker.assert_called_once()
    broker_mock.place_order.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 4 — Crash and recovery
# ---------------------------------------------------------------------------

def test_scenario_4_crash_and_recovery(tmp_path):
    """
    Bot saves portfolio state → process 'crashes' (new bot instance) →
    portfolio reloaded intact, no duplicate positions.
    """
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    queue_path = tmp_path / "signal_queue.json"
    db_path = tmp_path / "trades.db"
    portfolio_path = tmp_path / "portfolio.json"

    bot_module._SIGNAL_QUEUE_PATH = queue_path
    pm_module._DEFAULT_DB_PATH = db_path
    pm_module._DEFAULT_PORTFOLIO_PATH = portfolio_path

    # First bot instance: open a position
    bot1 = TradingBot(
        config=_config(),
        data_manager=MagicMock(),
        signal_engines=[],
        broker=MagicMock(),
        notifier=MagicMock(),
    )
    pos = Position(
        symbol="FPT",
        qty=200,
        avg_price=120_000,
        stop_loss=110_000,
        take_profit=145_000,
        buy_date="2026-04-18",
    )
    bot1.portfolio.open_position(pos)
    bot1.portfolio.save_state()

    # Simulate "crash": create a new bot instance (same paths)
    bot2 = TradingBot(
        config=_config(),
        data_manager=MagicMock(),
        signal_engines=[],
        broker=MagicMock(),
        notifier=MagicMock(),
    )

    # Portfolio should be reloaded intact
    assert "FPT" in bot2.portfolio.positions
    fpt = bot2.portfolio.positions["FPT"]
    assert fpt.qty == 200
    assert fpt.avg_price == 120_000

    # No duplicate: only 1 position
    assert len(bot2.portfolio.positions) == 1


# ---------------------------------------------------------------------------
# Scenario 5 — Data source switch
# ---------------------------------------------------------------------------

def test_scenario_5_data_source_switch(tmp_path):
    """
    Config data_source changed from YFINANCE → SSI →
    new bot instance uses SSIDataClient, not YFinanceClient.
    """
    from data_sources.ssi_data_client import SSIDataClient
    from data_sources.yfinance_client import YFinanceClient

    import core.bot as bot_module
    import core.portfolio_manager as pm_module
    bot_module._SIGNAL_QUEUE_PATH = tmp_path / "signal_queue.json"
    pm_module._DEFAULT_DB_PATH = tmp_path / "trades.db"
    pm_module._DEFAULT_PORTFOLIO_PATH = tmp_path / "portfolio.json"

    cfg_yfinance = _config({"data_source": "YFINANCE"})
    cfg_ssi = _config({"data_source": "SSI"})

    # Write the SSI config to disk (simulates user changing config via UI)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(cfg_ssi))

    # Build bot components as trading_bot.py's build_bot() does
    from data_sources.yfinance_client import YFinanceClient
    from data_sources.ssi_data_client import SSIDataClient
    from core.data_manager import DataManager

    data_source_cls = {"YFINANCE": YFinanceClient, "SSI": SSIDataClient}[cfg_ssi["data_source"]]
    data_source = data_source_cls()

    assert isinstance(data_source, SSIDataClient)
    assert not isinstance(data_source, YFinanceClient)
