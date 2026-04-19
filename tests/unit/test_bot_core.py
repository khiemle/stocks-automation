"""Unit tests for TradingBot and ENGINE_REGISTRY (Week 6)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from core.bot import Signal, TradingBot
from core.portfolio_manager import Position
from signals.registry import ENGINE_REGISTRY


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bot(tmp_path: Path, config_overrides: dict | None = None) -> TradingBot:
    """Build a TradingBot with fully mocked dependencies."""
    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal_engines": [{"name": "MomentumV1", "enabled": True, "weight": 1.0}],
        "signal": {"min_score": 0.55, "min_volume_ma20": 100_000},
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
    dm.get_universe.return_value = []
    broker = MagicMock()
    broker.get_order_status.side_effect = Exception("no orders")

    engine = MagicMock()
    engine.name = "MomentumV1"

    # Redirect state files to tmp_path
    import core.bot as bot_module
    import core.portfolio_manager as pm_module
    monkeypatch_paths(bot_module, pm_module, tmp_path)

    return TradingBot(config=config, data_manager=dm, signal_engines=[engine], broker=broker)


def monkeypatch_paths(bot_module, pm_module, tmp_path: Path) -> None:
    """Redirect file paths to isolated tmp_path and bypass time-of-day guard."""
    bot_module._SIGNAL_QUEUE_PATH = tmp_path / "signal_queue.json"
    bot_module._SKIP_TRADING_HOURS_CHECK = True
    pm_module._DEFAULT_DB_PATH = tmp_path / "trades.db"
    pm_module._DEFAULT_PORTFOLIO_PATH = tmp_path / "portfolio.json"


# ---------------------------------------------------------------------------
# ENGINE_REGISTRY
# ---------------------------------------------------------------------------

def test_engine_registry_has_momentum_v1():
    """ENGINE_REGISTRY phải đăng ký MomentumV1."""
    assert "MomentumV1" in ENGINE_REGISTRY
    assert ENGINE_REGISTRY["MomentumV1"] is not None


# ---------------------------------------------------------------------------
# build_bot DI
# ---------------------------------------------------------------------------

def test_build_bot_injects_yfinance_client(tmp_path):
    """config data_source=YFINANCE → bot.data_manager uses YFinanceClient."""
    from trading_bot import build_bot
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal_engines": [{"name": "MomentumV1", "enabled": True, "weight": 1.0}],
        "signal": {"min_score": 0.55},
        "scheduler": {},
        "telegram": {"enabled": False},
        "watchlist": [],
        "mode": "PAPER",
    }
    from data_sources.yfinance_client import YFinanceClient
    bot = build_bot(config)
    assert isinstance(bot._dm.data_source, YFinanceClient)


def test_build_bot_injects_simulated_broker(tmp_path):
    """config broker=SimulatedBroker → bot._broker is SimulatedBroker."""
    from trading_bot import build_bot
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal_engines": [{"name": "MomentumV1", "enabled": True, "weight": 1.0}],
        "signal": {"min_score": 0.55},
        "scheduler": {},
        "telegram": {"enabled": False},
        "watchlist": [],
        "mode": "PAPER",
    }
    from brokers.simulated_broker import SimulatedBroker
    bot = build_bot(config)
    assert isinstance(bot._broker, SimulatedBroker)


def test_build_bot_unknown_engine_raises_key_error(tmp_path):
    """Engine không có trong registry → KeyError rõ ràng."""
    from trading_bot import build_bot
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal_engines": [{"name": "UnknownEngine", "enabled": True, "weight": 1.0}],
        "signal": {"min_score": 0.55},
        "scheduler": {},
        "telegram": {"enabled": False},
        "watchlist": [],
        "mode": "PAPER",
    }
    with pytest.raises(KeyError):
        build_bot(config)


# ---------------------------------------------------------------------------
# daily_scan_job
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 300) -> pd.DataFrame:
    """Synthetic trending OHLCV, volume spike on last 3 bars to pass vol gate."""
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    close = np.linspace(50_000.0, 55_000.0, n)
    high = close * 1.002
    low = close * 0.998
    vol = np.full(n, 600_000.0)
    vol[-3:] = 1_500_000.0
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": vol}, index=idx)


def test_daily_scan_writes_pending_signals(tmp_path):
    """daily_scan_job với mock engine BUY → signal_queue.json chứa PENDING signal."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    from core.bot import Signal, TradingBot
    from core.protocols import SignalResult

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal_engines": [{"name": "MomentumV1", "enabled": True, "weight": 1.0}],
        "signal": {"min_score": 0.55},
        "scheduler": {},
        "telegram": {"enabled": False},
        "watchlist": [],
        "mode": "PAPER",
    }

    dm = MagicMock()
    dm.get_universe.return_value = ["VCB"]
    dm.get_ohlcv.return_value = _make_ohlcv()

    broker = MagicMock()
    broker.get_order_status.side_effect = Exception("no orders")

    engine = MagicMock()
    engine.name = "MomentumV1"
    engine.is_eligible.return_value = (True, "")
    engine.evaluate.return_value = SignalResult(
        score=0.70, regime="TRENDING", action="BUY",
        confidence=0.85,
        indicators={"close": 55_000, "atr": 1_000, "ema20": 54_000,
                    "ema60": 52_000, "ema200": 50_000,
                    "macd": 100, "macd_signal": 80,
                    "rsi": 62, "adx": 30, "adx_pos": 28, "adx_neg": 15,
                    "vol_ma20": 600_000, "vol_ratio": 2.5},
    )

    bot = TradingBot(config=config, data_manager=dm, signal_engines=[engine], broker=broker)

    with patch("core.bot.MarketRegime") as mock_regime:
        mock_regime.return_value.context.return_value = {"macro_above_ema50": True}
        bot.daily_scan_job()

    queue_path = bot_module._SIGNAL_QUEUE_PATH
    assert queue_path.exists()
    signals = json.loads(queue_path.read_text())
    assert len(signals) == 1
    assert signals[0]["symbol"] == "VCB"
    assert signals[0]["status"] == "PENDING"
    assert signals[0]["action"] == "BUY"
    assert signals[0]["source"] == "EOD"


# ---------------------------------------------------------------------------
# signal_expiry_job
# ---------------------------------------------------------------------------

def test_signal_expiry_marks_old_signals_expired(tmp_path):
    """PENDING signal từ hôm qua → EXPIRED sau khi gọi signal_expiry_job."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    from core.bot import Signal, TradingBot

    dm = MagicMock()
    dm.get_universe.return_value = []
    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE", "broker": "SimulatedBroker",
        "signal_engines": [], "signal": {}, "scheduler": {},
        "telegram": {"enabled": False}, "watchlist": [], "mode": "PAPER",
    }
    bot = TradingBot(config=config, data_manager=dm, signal_engines=[], broker=broker)

    yesterday = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    old_sig = Signal(
        symbol="HPG", action="BUY", score=0.65, engine="MomentumV1",
        source="EOD", created_at=yesterday, stop_loss=40_000, take_profit=50_000,
        status="PENDING",
    )
    bot._queue = [old_sig]
    bot.signal_expiry_job()

    assert bot._queue[0].status == "EXPIRED"


# ---------------------------------------------------------------------------
# order_placement_job
# ---------------------------------------------------------------------------

def test_order_placement_skips_pending_signals(tmp_path):
    """Chỉ đặt lệnh cho APPROVED, bỏ qua PENDING."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    from core.bot import Signal, TradingBot
    from core.protocols import OrderResult

    dm = MagicMock()
    dm.get_universe.return_value = []
    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()
    broker.place_order.return_value = OrderResult(
        order_id="ord-001", status="SIMULATED", message="ok"
    )

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE", "broker": "SimulatedBroker",
        "signal_engines": [], "signal": {}, "scheduler": {},
        "telegram": {"enabled": False}, "watchlist": [], "mode": "PAPER",
    }
    bot = TradingBot(config=config, data_manager=dm, signal_engines=[], broker=broker)

    pending = Signal(
        symbol="VCB", action="BUY", score=0.65, engine="MomentumV1",
        source="EOD", created_at=datetime.now().isoformat(),
        stop_loss=45_000, take_profit=55_000, status="PENDING",
        indicators={"close": 50_000, "atr": 1_000},
    )
    approved = Signal(
        symbol="HPG", action="BUY", score=0.70, engine="MomentumV1",
        source="EOD", created_at=datetime.now().isoformat(),
        stop_loss=38_000, take_profit=48_000, status="APPROVED",
        indicators={"close": 42_000, "atr": 800},
    )
    bot._queue = [pending, approved]
    bot.order_placement_job()

    assert pending.status == "PENDING"
    assert approved.status == "ORDER_PLACED"
    # broker.place_order called exactly once (for the APPROVED signal)
    assert broker.place_order.call_count == 1


# ---------------------------------------------------------------------------
# cancel_unfilled_job
# ---------------------------------------------------------------------------

def test_cancel_unfilled_called_after_1430(tmp_path):
    """cancel_unfilled_job → broker.cancel_order() được gọi cho ORDER_PLACED."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    from core.bot import Signal, TradingBot

    dm = MagicMock()
    dm.get_universe.return_value = []
    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()
    broker.cancel_order.return_value = True

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE", "broker": "SimulatedBroker",
        "signal_engines": [], "signal": {}, "scheduler": {},
        "telegram": {"enabled": False}, "watchlist": [], "mode": "PAPER",
    }
    bot = TradingBot(config=config, data_manager=dm, signal_engines=[], broker=broker)

    sig = Signal(
        symbol="FPT", action="BUY", score=0.60, engine="MomentumV1",
        source="EOD", created_at=datetime.now().isoformat(),
        stop_loss=50_000, take_profit=60_000, status="ORDER_PLACED",
        id="ord-abc",
    )
    bot._queue = [sig]
    bot.cancel_unfilled_job()

    broker.cancel_order.assert_called_once_with("ord-abc", account="paper")
    assert sig.status == "REJECTED"


# ---------------------------------------------------------------------------
# intraday_monitor: stop / TP / trailing
# ---------------------------------------------------------------------------

def _make_position(symbol="VCB", stop=45_000, tp=55_000,
                   avg=50_000, atr=1_000, trail=False) -> Position:
    return Position(
        symbol=symbol, qty=1000, avg_price=avg,
        stop_loss=stop, take_profit=tp,
        buy_date=(date.today() - timedelta(days=3)).isoformat(),
        engine="MomentumV1",
        entry_atr=atr,
        trail_active=trail,
    )


def test_intraday_monitor_triggers_sell_on_stop(tmp_path):
    """current_price <= stop_loss → place_order(SELL) được gọi."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    from core.bot import TradingBot
    from core.protocols import OrderResult

    dm = MagicMock()
    dm.get_universe.return_value = []
    dm.data_source.get_intraday_prices_batch.return_value = {"VCB": 44_000}  # below stop

    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()
    broker.place_order.return_value = OrderResult("ord-x", "SIMULATED", "ok")

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE", "broker": "SimulatedBroker",
        "signal_engines": [], "signal": {"min_score": 0.55}, "scheduler": {},
        "telegram": {"enabled": False}, "watchlist": ["VCB"], "mode": "PAPER",
    }
    bot = TradingBot(config=config, data_manager=dm, signal_engines=[], broker=broker)
    pos = _make_position()
    bot._portfolio._positions["VCB"] = pos
    bot._portfolio._cash = 490_000_000

    bot.intraday_monitor_job()

    assert broker.place_order.call_count == 1
    call_kwargs = broker.place_order.call_args
    assert call_kwargs[1].get("side") == "S" or call_kwargs[0][1] == "S"


def test_intraday_monitor_triggers_sell_on_tp(tmp_path):
    """current_price >= take_profit → place_order(SELL) được gọi."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    from core.bot import TradingBot
    from core.protocols import OrderResult

    dm = MagicMock()
    dm.get_universe.return_value = []
    dm.data_source.get_intraday_prices_batch.return_value = {"VCB": 56_000}  # above TP

    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()
    broker.place_order.return_value = OrderResult("ord-y", "SIMULATED", "ok")

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE", "broker": "SimulatedBroker",
        "signal_engines": [], "signal": {"min_score": 0.55}, "scheduler": {},
        "telegram": {"enabled": False}, "watchlist": [], "mode": "PAPER",
    }
    bot = TradingBot(config=config, data_manager=dm, signal_engines=[], broker=broker)
    pos = _make_position()
    bot._portfolio._positions["VCB"] = pos
    bot._portfolio._cash = 490_000_000

    bot.intraday_monitor_job()

    assert broker.place_order.call_count == 1


def test_intraday_trailing_stop_updates(tmp_path):
    """price tăng > entry + 1R → trail_active=True, stop_loss mới trong portfolio."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    from core.bot import TradingBot
    from core.risk_engine import RiskEngine

    avg_price = 50_000.0
    atr = 1_000.0
    # price just above entry + 1R trigger (= 50_000 + 1.5*1_000 = 51_500)
    current_price = 52_000.0

    dm = MagicMock()
    dm.get_universe.return_value = []
    dm.data_source.get_intraday_prices_batch.return_value = {"VCB": current_price}

    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE", "broker": "SimulatedBroker",
        "signal_engines": [], "signal": {"min_score": 0.55}, "scheduler": {},
        "telegram": {"enabled": False}, "watchlist": [], "mode": "PAPER",
    }
    bot = TradingBot(config=config, data_manager=dm, signal_engines=[], broker=broker)
    pos = _make_position(stop=avg_price - 1.5 * atr, tp=avg_price + 4.5 * atr,
                         avg=avg_price, atr=atr, trail=False)
    bot._portfolio._positions["VCB"] = pos
    bot._portfolio._cash = 490_000_000

    bot.intraday_monitor_job()

    updated_pos = bot._portfolio.positions.get("VCB")
    assert updated_pos is not None
    expected_new_stop = current_price - RiskEngine.ATR_TRAIL_MULT * atr  # 52_000 - 2_000 = 50_000
    assert updated_pos.stop_loss >= expected_new_stop - 1  # allow float rounding
    assert updated_pos.trail_active is True


# ---------------------------------------------------------------------------
# Watchlist intraday signal
# ---------------------------------------------------------------------------

def test_watchlist_intraday_signal_created_when_score_high(tmp_path):
    """score=0.63 trên watchlist → INTRADAY signal được thêm vào queue."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    from core.bot import TradingBot
    from core.protocols import SignalResult

    dm = MagicMock()
    dm.get_universe.return_value = []
    dm.data_source.get_intraday_prices_batch.return_value = {}
    dm.get_ohlcv.return_value = _make_ohlcv()

    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()

    engine = MagicMock()
    engine.name = "MomentumV1"
    engine.evaluate.return_value = SignalResult(
        score=0.63, regime="TRENDING", action="BUY", confidence=0.80,
        indicators={"close": 55_000, "atr": 1_000, "ema20": 54_000, "ema60": 52_000,
                    "ema200": 50_000, "macd": 100, "macd_signal": 80,
                    "rsi": 62, "adx": 30, "adx_pos": 28, "adx_neg": 15,
                    "vol_ma20": 600_000, "vol_ratio": 2.5},
    )

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE", "broker": "SimulatedBroker",
        "signal_engines": [{"name": "MomentumV1", "enabled": True}],
        "signal": {"min_score": 0.55}, "scheduler": {},
        "telegram": {"enabled": False},
        "watchlist": ["FPT"],  # FPT in watchlist
        "mode": "PAPER",
    }
    bot = TradingBot(config=config, data_manager=dm, signal_engines=[engine], broker=broker)

    bot.intraday_monitor_job()

    intraday_signals = [s for s in bot.queue if s.source == "INTRADAY" and s.symbol == "FPT"]
    assert len(intraday_signals) == 1
    assert intraday_signals[0].status == "PENDING"


# ---------------------------------------------------------------------------
# State recovery
# ---------------------------------------------------------------------------

def test_recover_state_restores_portfolio(tmp_path):
    """portfolio.json tồn tại → positions load đúng khi khởi động bot."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    # Write a pre-existing portfolio.json
    portfolio_path = pm_module._DEFAULT_PORTFOLIO_PATH
    portfolio_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "cash": 450_000_000,
        "equity_week_start": 500_000_000,
        "week_start_date": date.today().isoformat(),
        "positions": {
            "VCB": {
                "symbol": "VCB", "qty": 1000, "avg_price": 50_000,
                "stop_loss": 47_500, "take_profit": 54_500,
                "buy_date": date.today().isoformat(),
                "engine": "MomentumV1",
                "entry_atr": 1_000, "trail_active": False,
            }
        },
    }
    portfolio_path.write_text(json.dumps(state))

    dm = MagicMock()
    dm.get_universe.return_value = []
    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE", "broker": "SimulatedBroker",
        "signal_engines": [], "signal": {}, "scheduler": {},
        "telegram": {"enabled": False}, "watchlist": [], "mode": "PAPER",
    }
    bot = TradingBot(config=config, data_manager=dm, signal_engines=[], broker=broker)

    assert "VCB" in bot.portfolio.positions
    assert bot.portfolio.cash == 450_000_000
    assert bot.portfolio.positions["VCB"].qty == 1000


def test_recover_state_syncs_pending_orders(tmp_path):
    """ORDER_PLACED signal → recover_state() gọi get_order_status để sync."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    monkeypatch_paths(bot_module, pm_module, tmp_path)

    from core.bot import Signal
    from core.protocols import OrderStatus

    # Pre-write a signal_queue with ORDER_PLACED signal
    queue_path = bot_module._SIGNAL_QUEUE_PATH
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    placed_sig = {
        "id": "ord-recover-001",
        "symbol": "HPG", "action": "BUY", "score": 0.65,
        "engine": "MomentumV1", "source": "EOD",
        "created_at": datetime.now().isoformat(),
        "stop_loss": 38_000, "take_profit": 48_000,
        "indicators": {}, "status": "ORDER_PLACED",
    }
    queue_path.write_text(json.dumps([placed_sig]))

    dm = MagicMock()
    dm.get_universe.return_value = []

    broker = MagicMock()
    broker.get_order_status.return_value = OrderStatus(
        order_id="ord-recover-001", status="FILLED",
        filled_qty=1000, fill_price=42_000,
    )

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE", "broker": "SimulatedBroker",
        "signal_engines": [], "signal": {}, "scheduler": {},
        "telegram": {"enabled": False}, "watchlist": [], "mode": "PAPER",
    }
    bot = TradingBot(config=config, data_manager=dm, signal_engines=[], broker=broker)

    broker.get_order_status.assert_called_once_with("ord-recover-001")
    assert bot.queue[0].status == "FILLED"
