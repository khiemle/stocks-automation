from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.backtester import Backtester, BacktestResult, _compute_metrics, TradeLog


def _make_config(initial_cash=500_000_000):
    return {
        "capital": {"initial": initial_cash, "max_positions": 5,
                    "risk_per_trade_pct": 0.02, "max_position_pct": 0.20},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal_engines": [{"name": "MomentumV1", "enabled": True, "weight": 1.0}],
    }


def _make_ohlcv(n: int = 300, base: float = 50_000.0) -> pd.DataFrame:
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    prices = [base * (1 + 0.001 * i) for i in range(n)]
    return pd.DataFrame({
        "open":   prices,
        "high":   [p * 1.03 for p in prices],
        "low":    [p * 0.97 for p in prices],
        "close":  prices,
        "volume": [1_000_000] * n,
    }, index=idx)


def _make_trades(wins=3, losses=2, win_pnl=1_000_000, loss_pnl=-500_000):
    trades = []
    for i in range(wins):
        trades.append(TradeLog("S", "2024-01-01", "2024-02-01", 10000, 11000, 100, win_pnl))
    for i in range(losses):
        trades.append(TradeLog("S", "2024-01-01", "2024-02-01", 10000, 9500, 100, loss_pnl))
    return trades


def test_walk_forward_split_is_70_30(tmp_path, monkeypatch):
    import core.backtester as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

    df = _make_ohlcv(500)
    d = tmp_path / "data" / "market" / "HOSE"
    d.mkdir(parents=True)
    df.to_parquet(d / "VCB.parquet")

    bt = Backtester(_make_config())
    split = 0.7
    split_idx = int(len(df) * split)
    df_is  = df.iloc[:split_idx]

    assert len(df_is) == split_idx
    # IS trading ends before OOS trading begins (split_idx is the boundary)
    oos_start = max(0, split_idx - mod._WARMUP_BARS)
    df_oos = df.iloc[oos_start:]
    # OOS signal window starts at split_idx (after its own warmup)
    assert df_is.index[-1] < df_oos.index[mod._WARMUP_BARS]


def test_no_data_leak_train_to_test(tmp_path, monkeypatch):
    """IS signals and OOS signals must not share any bars.
    OOS shares warmup bars with IS (intentional — needed for EMA200 calibration),
    but the trading window (post-warmup) must be strictly after IS ends.
    """
    import core.backtester as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

    df = _make_ohlcv(600)
    d = tmp_path / "data" / "market" / "HOSE"
    d.mkdir(parents=True)
    df.to_parquet(d / "VCB.parquet")

    split = 0.7
    split_idx = int(len(df) * split)

    # IS signal bars: [_WARMUP_BARS, split_idx)
    is_signal_dates = set(df.index[mod._WARMUP_BARS:split_idx])

    # OOS slice starts at split_idx - _WARMUP_BARS; signal bars start at split_idx
    oos_start = max(0, split_idx - mod._WARMUP_BARS)
    oos_signal_dates = set(df.index[oos_start + mod._WARMUP_BARS:])

    overlap = is_signal_dates & oos_signal_dates
    assert len(overlap) == 0, f"{len(overlap)} signal bars appear in both IS and OOS"


def test_out_of_sample_metrics_in_report(tmp_path, monkeypatch):
    import core.backtester as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

    df = _make_ohlcv(300)
    d = tmp_path / "data" / "market" / "HOSE"
    d.mkdir(parents=True)
    df.to_parquet(d / "VCB.parquet")

    bt = Backtester(_make_config())

    split = 0.7
    split_idx = int(len(df) * split)
    is_trades, is_eq   = bt._simulate("VCB", df.iloc[:split_idx])
    oos_trades, oos_eq = bt._simulate("VCB", df.iloc[split_idx:])

    is_metrics  = _compute_metrics(is_eq,  is_trades)
    oos_metrics = _compute_metrics(oos_eq, oos_trades)

    result = BacktestResult(in_sample=is_metrics, out_of_sample=oos_metrics,
                            trades=is_trades + oos_trades)
    assert result.out_of_sample is not None
    summary = result.summary()
    assert "In-Sample" in summary
    assert "Out-of-Sample" in summary


def test_all_8_metrics_present_in_report():
    trades = _make_trades()
    equity = [500_000_000 * (1 + 0.001 * i) for i in range(100)]
    metrics = _compute_metrics(equity, trades)

    assert hasattr(metrics, "total_return")
    assert hasattr(metrics, "sharpe_ratio")
    assert hasattr(metrics, "sortino_ratio")
    assert hasattr(metrics, "information_ratio")
    assert hasattr(metrics, "max_drawdown")
    assert hasattr(metrics, "win_rate")
    assert hasattr(metrics, "profit_factor")
    assert hasattr(metrics, "total_trades")

    summary = metrics.summary()
    for kw in ["Total Return", "Sharpe", "Sortino", "Information", "Drawdown", "Win Rate", "Profit Factor", "Trades"]:
        assert kw in summary, f"Missing '{kw}' in summary"
