"""
Integration tests for Signal + Risk Engine.
These tests load real Parquet data (must run init-data first).
Marked pytest.mark.integration — skipped in CI if data not present.
Run: pytest tests/integration/test_signal_risk.py -v
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from signals.momentum_v1 import MomentumV1
from core.risk_engine import RiskEngine

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# test_scan_single_symbol_end_to_end
# ---------------------------------------------------------------------------

def test_scan_single_symbol_end_to_end(tmp_path, monkeypatch):
    """Load synthetic Parquet for VCB, run MomentumV1, get valid SignalResult."""
    import core.data_manager as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "market")

    # Write synthetic parquet
    parquet_dir = tmp_path / "market" / "HOSE"
    parquet_dir.mkdir(parents=True)
    n = 120
    close = np.array([50_000 + 30 * i for i in range(n)], dtype=float)
    # Add pullbacks to keep RSI < 100
    for i in range(n):
        if i % 4 == 3:
            close[i] = close[i] * 0.997

    df = pd.DataFrame({
        "open": close,
        "high": close * 1.002,
        "low": close * 0.998,
        "close": close,
        "volume": np.full(n, 500_000.0),
    }, index=pd.date_range("2025-01-02", periods=n, freq="B"))
    df.to_parquet(parquet_dir / "VCB.parquet")

    from core.data_manager import DataManager
    from unittest.mock import MagicMock
    dm = DataManager(MagicMock())
    raw = dm.get_ohlcv("VCB", days=n)

    engine = MomentumV1()
    result = engine.evaluate(raw, foreign_flow=None)

    # Validate structure
    assert result is not None
    assert result.regime in ("TRENDING", "VOLATILE", "SIDEWAYS")
    assert result.action in ("BUY", "SELL", "HOLD")
    assert -1.0 <= result.score <= 1.0
    assert 0.0 <= result.confidence <= 1.0
    assert "ema20" in result.indicators
    assert "rsi" in result.indicators
    assert "adx" in result.indicators
    assert "atr" in result.indicators


# ---------------------------------------------------------------------------
# test_risk_engine_with_real_atr
# ---------------------------------------------------------------------------

def test_risk_engine_with_real_atr(tmp_path, monkeypatch):
    """Compute ATR from synthetic VCB data, derive position size, validate bounds."""
    import core.data_manager as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "market")

    parquet_dir = tmp_path / "market" / "HOSE"
    parquet_dir.mkdir(parents=True)
    n = 120
    close = np.linspace(50_000, 55_000, n)
    high = close * 1.003
    low = close * 0.997
    df = pd.DataFrame({
        "open": close, "high": high, "low": low,
        "close": close, "volume": np.full(n, 500_000.0),
    }, index=pd.date_range("2025-01-02", periods=n, freq="B"))
    df.to_parquet(parquet_dir / "VCB.parquet")

    from core.data_manager import DataManager
    from ta.volatility import AverageTrueRange
    from unittest.mock import MagicMock

    dm = DataManager(MagicMock())
    raw = dm.get_ohlcv("VCB", days=n)

    atr_series = AverageTrueRange(raw["high"], raw["low"], raw["close"], window=14).average_true_range()
    atr_val = float(atr_series.iloc[-1])
    close_val = float(raw["close"].iloc[-1])

    capital = 500_000_000
    eng = RiskEngine(backtest_mdd=0.10, capital=capital)
    result = eng.compute_position_size(close_val, atr_val, exchange="HOSE")

    if result.eligible:
        # Stop price within HOSE band
        assert result.stop_price >= close_val * 0.93, (
            f"stop {result.stop_price} < 93% of close {close_val}"
        )
        # Take profit is ATR × 4.5 above entry
        assert result.take_profit == pytest.approx(close_val + atr_val * 4.5, rel=1e-6)
        # Position value <= 20% of capital
        position_value = result.shares * close_val
        assert position_value <= capital * 0.20 * 1.01  # +1% tolerance for lot rounding
        # ATR and stop are sensible
        assert atr_val > 0
        assert result.stop_distance == pytest.approx(atr_val * 1.5, rel=1e-6)
    else:
        # If not eligible, it's because ATR is very small (synthetic data) → warn message present
        assert len(result.warnings) > 0
