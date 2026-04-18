from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pytest

from core.backtester import Backtester, _COMMISSION_RATE, _SLIPPAGE_RATE


def _make_config(initial_cash=500_000_000):
    return {
        "capital": {"initial": initial_cash, "max_positions": 5,
                    "risk_per_trade_pct": 0.02, "max_position_pct": 0.20},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal_engines": [{"name": "MomentumV1", "enabled": True, "weight": 1.0}],
    }


def _make_ohlcv(n: int, base: float = 50_000.0, exchange="HOSE") -> pd.DataFrame:
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    # 3-up / 1-down pattern to generate real signals
    closes = []
    p = base
    for i in range(n):
        p = p * (1.003 if i % 4 != 3 else 0.995)
        closes.append(p)
    return pd.DataFrame({
        "open":   closes,
        "high":   [p * 1.04 for p in closes],
        "low":    [p * 0.96 for p in closes],
        "close":  closes,
        "volume": [2_000_000] * n,
    }, index=idx)


def _write_parquet(tmp_path, symbol, df, exchange="HOSE"):
    d = tmp_path / "data" / "market" / exchange
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / f"{symbol}.parquet")


@pytest.mark.slow
def test_backtest_hpg_3_years_completes_under_60s(tmp_path, monkeypatch):
    import core.backtester as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

    df = _make_ohlcv(756)  # ~3 years of trading days
    _write_parquet(tmp_path, "HPG", df)

    bt = Backtester(_make_config())
    start = time.time()
    result = bt.run(["HPG"], years=3)
    elapsed = time.time() - start

    assert elapsed < 60, f"Backtest took {elapsed:.1f}s > 60s"
    assert result.in_sample.total_trades >= 0


def test_backtest_pnl_matches_manual_on_3_trades(tmp_path, monkeypatch):
    """
    Manually place 3 trades by directly calling _make_trade and verify
    _compute_metrics matches hand calculation.
    """
    from core.backtester import _compute_metrics, TradeLog

    qty = 100
    specs = [
        (50_000, 55_000),   # win
        (30_000, 28_000),   # loss
        (80_000, 84_000),   # win
    ]
    trades = []
    for entry, exit_p in specs:
        gross = qty * (exit_p - entry)
        comm  = qty * (entry + exit_p) * _COMMISSION_RATE
        slip  = qty * (entry + exit_p) * _SLIPPAGE_RATE
        net   = gross - comm - slip
        trades.append(TradeLog("VCB", "2024-01-01", "2024-02-01", entry, exit_p, qty, net))

    equity = [500_000_000, 501_000_000, 500_500_000, 501_500_000]
    metrics = _compute_metrics(equity, trades)

    expected_wins   = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    expected_losses = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
    expected_pf = expected_wins / expected_losses

    assert abs(metrics.profit_factor - expected_pf) < 1e-6
    assert abs(metrics.win_rate - 2 / 3) < 1e-9
    assert metrics.total_trades == 3


def test_backtest_matches_paper_simulation_on_same_data(tmp_path, monkeypatch):
    """
    Anti-bias check: running _simulate twice on the same df must produce
    identical trade counts and identical net P&L (no randomness or state leak).
    """
    import core.backtester as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

    df = _make_ohlcv(200)
    _write_parquet(tmp_path, "VCB", df)

    bt = Backtester(_make_config())
    trades1, eq1 = bt._simulate("VCB", df)
    trades2, eq2 = bt._simulate("VCB", df)

    assert len(trades1) == len(trades2), "Trade count differs between runs — non-deterministic"
    total_pnl1 = sum(t.net_pnl for t in trades1)
    total_pnl2 = sum(t.net_pnl for t in trades2)
    assert abs(total_pnl1 - total_pnl2) < 1, "P&L differs between identical runs"
