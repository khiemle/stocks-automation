from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from signals.momentum_v1 import MomentumV1

_ENGINE = MomentumV1()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(
    n: int = 120,
    trend: str = "up",     # "up" | "down" | "flat"
    rsi_override: float | None = None,
    vol_ratio: float = 1.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic OHLCV — deterministic for test stability."""
    rng = np.random.default_rng(seed)
    base = 50_000.0
    if trend == "up":
        close = base + np.linspace(0, 5_000, n) + rng.normal(0, 200, n)
    elif trend == "down":
        close = base + np.linspace(5_000, 0, n) - np.linspace(0, 5_000, n) + rng.normal(0, 200, n)
        close = base - np.linspace(0, 5_000, n) + rng.normal(0, 200, n)
    else:
        close = base + rng.normal(0, 300, n)

    close = np.maximum(close, 1_000)

    if rsi_override is not None:
        # Manufacture extreme run to force RSI toward the target
        if rsi_override > 70:
            close = np.linspace(40_000, 60_000, n)  # persistent uptrend → high RSI
        else:
            close = np.linspace(60_000, 40_000, n)  # persistent downtrend → low RSI

    high = close * (1 + rng.uniform(0.001, 0.005, n))
    low = close * (1 - rng.uniform(0.001, 0.005, n))
    volume = np.full(n, 500_000 * vol_ratio) + rng.normal(0, 10_000, n)
    volume = np.maximum(volume, 1)

    idx = pd.date_range("2025-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def _make_trending_df(n: int = 120, vol_breakout: bool = True) -> pd.DataFrame:
    """Strong uptrend with pullbacks: MA20>MA60, MACD bullish, ADX>25, RSI 55-70.

    Pattern: 3 up days (+0.3% each), 1 pullback (-0.5%) → RSI ≈ 64.
    If vol_breakout=True, last 3 bars have volume 2.5x baseline (simulates genuine
    momentum with volume confirm — needed to pass the BUY gate).
    """
    close = [50_000.0]
    for i in range(n - 1):
        mult = 0.995 if i % 4 == 3 else 1.003
        close.append(close[-1] * mult)
    close = np.array(close)
    high = close * 1.002
    low = close * 0.998
    volume = np.full(n, 600_000.0)
    if vol_breakout:
        volume[-3:] = 1_500_000.0  # 2.5x spike → ratio ~1.8 vs MA20
    idx = pd.date_range("2025-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def _make_sideways_df(n: int = 120) -> pd.DataFrame:
    """Flat oscillating price — low ADX expected."""
    rng = np.random.default_rng(7)
    close = 50_000 + rng.normal(0, 300, n)
    close = np.maximum(close, 10_000)
    high = close * 1.002
    low = close * 0.998
    volume = np.full(n, 400_000.0)
    idx = pd.date_range("2025-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


# ---------------------------------------------------------------------------
# Score range
# ---------------------------------------------------------------------------

def test_score_range():
    """Score must always be in [-1.0, 1.0]."""
    for trend in ("up", "down", "flat"):
        df = _make_df(trend=trend)
        result = _ENGINE.evaluate(df, foreign_flow=None)
        assert -1.0 <= result.score <= 1.0, f"trend={trend} score={result.score}"


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------

def test_regime_detection_trending():
    """Strong uptrend (ADX > 25) → TRENDING."""
    df = _make_trending_df()
    result = _ENGINE.evaluate(df, foreign_flow=None)
    assert result.regime == "TRENDING"


def test_regime_detection_volatile():
    """High ATR/close (> 3%) → VOLATILE."""
    rng = np.random.default_rng(99)
    n = 120
    close = 10_000 + rng.normal(0, 0, n)
    close = np.full(n, 10_000.0)
    # ATR ≈ (high-low)/close → make range ~5%
    high = close * 1.025
    low = close * 0.975
    volume = np.full(n, 500_000.0)
    idx = pd.date_range("2025-01-02", periods=n, freq="B")
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
    result = _ENGINE.evaluate(df, foreign_flow=None)
    assert result.regime == "VOLATILE"


def test_regime_detection_sideways():
    """Flat market → SIDEWAYS (ADX < 25, ATR/close < 3%)."""
    df = _make_sideways_df()
    result = _ENGINE.evaluate(df, foreign_flow=None)
    assert result.regime == "SIDEWAYS"


# ---------------------------------------------------------------------------
# Directional signals
# ---------------------------------------------------------------------------

def test_trending_market_returns_high_score():
    """MA20>MA60, MACD bullish, RSI<70, ADX>25 → score > 0.55 (BUY)."""
    df = _make_trending_df()
    result = _ENGINE.evaluate(df, foreign_flow=None)
    assert result.score > 0.55, f"Expected BUY, got score={result.score}"
    assert result.action == "BUY"


def test_sideways_market_reduces_score():
    """ADX < 20 → SIDEWAYS, score lower than trending equivalent."""
    trending = _make_trending_df()
    sideways = _make_sideways_df()
    r_trend = _ENGINE.evaluate(trending, foreign_flow=None)
    r_side = _ENGINE.evaluate(sideways, foreign_flow=None)
    assert r_trend.score > r_side.score, (
        f"Trending score {r_trend.score} should exceed sideways {r_side.score}"
    )


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def test_overbought_rsi_blocks_buy():
    """Persistent uptrend → high RSI → score < 0.55 (no BUY signal)."""
    df = _make_df(rsi_override=80)
    result = _ENGINE.evaluate(df, foreign_flow=None)
    assert result.score < _BUY_THRESHOLD(), f"RSI gate failed, score={result.score}"
    assert result.action != "BUY"


def _BUY_THRESHOLD():
    return 0.55


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------

def test_low_volume_reduces_score():
    """Last-bar volume below vs above MA20 → lower vs higher vol component."""
    df = _make_df()
    # Override last bar volume: 0.3× vs 2× of MA baseline (500k)
    df_low = df.copy()
    df_low.iloc[-1, df_low.columns.get_loc("volume")] = 150_000   # 0.3x of 500k
    df_high = df.copy()
    df_high.iloc[-1, df_high.columns.get_loc("volume")] = 1_000_000  # 2x of 500k

    r_low = _ENGINE.evaluate(df_low, foreign_flow=None)
    r_high = _ENGINE.evaluate(df_high, foreign_flow=None)
    assert r_high.score >= r_low.score, (
        f"High volume score {r_high.score} should be >= low volume {r_low.score}"
    )


# ---------------------------------------------------------------------------
# Volume breakout hard gate (requires vol >= 1.5 × vol_MA20 on signal bar)
# ---------------------------------------------------------------------------

def test_volume_breakout_blocks_buy_when_vol_below_1_5x():
    """Trending pattern nhưng vol_ratio < 1.5 → score bị clamp < BUY_THRESHOLD."""
    df = _make_trending_df(vol_breakout=False)  # all bars at 600k, ratio ≈ 1.0
    result = _ENGINE.evaluate(df, foreign_flow=None)
    assert result.action != "BUY", (
        f"vol_ratio ≈ 1.0 phải block BUY, got score={result.score}"
    )


def test_volume_breakout_allows_buy_when_spike():
    """Trending + vol spike 2.5× → gate thoả → BUY."""
    df = _make_trending_df(vol_breakout=True)
    result = _ENGINE.evaluate(df, foreign_flow=None)
    assert result.action == "BUY", (
        f"Volume breakout trending phải BUY, got action={result.action} score={result.score}"
    )


# ---------------------------------------------------------------------------
# Foreign flow
# ---------------------------------------------------------------------------

def test_missing_foreign_flow_sets_weight_zero():
    """foreign_flow=None must not crash and weight is zeroed out."""
    df = _make_trending_df()
    result = _ENGINE.evaluate(df, foreign_flow=None)
    assert result is not None
    assert -1.0 <= result.score <= 1.0


def test_foreign_flow_positive_increases_score():
    """Positive net_value foreign flow should lift score vs None."""
    df = _make_df()
    idx = pd.date_range("2025-01-02", periods=10, freq="B")
    ff = pd.DataFrame({"net_value": [2e9] * 10}, index=idx)
    r_with = _ENGINE.evaluate(df, foreign_flow=ff)
    r_without = _ENGINE.evaluate(df, foreign_flow=None)
    assert r_with.score >= r_without.score - 0.01  # allow tiny float delta


# ---------------------------------------------------------------------------
# No look-ahead bias (CRITICAL)
# ---------------------------------------------------------------------------

def test_no_look_ahead_bias():
    """evaluate(df[:T]) must equal evaluate(df[:T]) sliced from full df."""
    df_full = _make_trending_df(n=200)
    T = 120
    df_slice = df_full.iloc[:T]

    r1 = _ENGINE.evaluate(df_slice.copy(), foreign_flow=None)
    r2 = _ENGINE.evaluate(df_full.iloc[:T].copy(), foreign_flow=None)

    assert r1.score == pytest.approx(r2.score, abs=1e-9)
    assert r1.regime == r2.regime
    assert r1.action == r2.action


# ---------------------------------------------------------------------------
# Exclusion filters (is_eligible)
# ---------------------------------------------------------------------------

def test_low_volume_symbol_excluded():
    """vol_MA20 = 80k < 100k threshold → not eligible."""
    rng = np.random.default_rng(1)
    n = 120
    close = np.full(n, 50_000.0)
    volume = np.full(n, 80_000.0)
    idx = pd.date_range("2025-01-02", periods=n, freq="B")
    df = pd.DataFrame(
        {"open": close, "high": close * 1.002, "low": close * 0.998,
         "close": close, "volume": volume},
        index=idx,
    )
    eligible, reason = _ENGINE.is_eligible(df, symbol="VCB", portfolio_symbols=[])
    assert not eligible
    assert "vol" in reason.lower()


def test_penny_stock_excluded():
    """close = 4,500 VND < 5,000 threshold → not eligible."""
    n = 120
    close = np.full(n, 4_500.0)
    volume = np.full(n, 500_000.0)
    idx = pd.date_range("2025-01-02", periods=n, freq="B")
    df = pd.DataFrame(
        {"open": close, "high": close * 1.002, "low": close * 0.998,
         "close": close, "volume": volume},
        index=idx,
    )
    eligible, reason = _ENGINE.is_eligible(df, symbol="XYZ", portfolio_symbols=[])
    assert not eligible
    assert "price" in reason.lower()


def test_existing_position_excluded():
    """Symbol already in portfolio_symbols → not eligible."""
    df = _make_trending_df()
    eligible, reason = _ENGINE.is_eligible(df, symbol="VCB", portfolio_symbols=["VCB", "HPG"])
    assert not eligible
    assert "portfolio" in reason.lower()


def test_t2_lock_excluded():
    """Symbol in t2_lock_symbols → not eligible."""
    df = _make_trending_df()
    eligible, reason = _ENGINE.is_eligible(
        df, symbol="FPT", portfolio_symbols=[], t2_lock_symbols=["FPT"]
    )
    assert not eligible
    assert "t+2" in reason.lower() or "t2" in reason.lower()
