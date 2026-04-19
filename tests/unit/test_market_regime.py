from __future__ import annotations

import pandas as pd
import pytest

from core.market_regime import MarketRegime


@pytest.fixture
def _stub_symbols(tmp_path, monkeypatch):
    """Build 3 synthetic symbols: uptrend, downtrend, flat — enough for basket + EMA50."""
    n = 200
    idx = pd.date_range("2024-01-02", periods=n, freq="B")

    market_dir = tmp_path / "market" / "HOSE"
    market_dir.mkdir(parents=True)

    # Uptrend: 50k → 80k
    up_vals = list(range(50_000, 50_000 + n * 150, 150))[:n]
    pd.DataFrame({"close": up_vals}, index=idx).to_parquet(market_dir / "UP.parquet")

    # Downtrend: 80k → 50k
    dn_vals = list(range(80_000, 80_000 - n * 150, -150))[:n]
    pd.DataFrame({"close": dn_vals}, index=idx).to_parquet(market_dir / "DN.parquet")

    # Flat around 60k
    pd.DataFrame({"close": [60_000.0] * n}, index=idx).to_parquet(market_dir / "FL.parquet")

    from core import market_regime as mr
    monkeypatch.setattr(mr, "_load_close_series",
                        lambda s: pd.read_parquet(market_dir / f"{s}.parquet")["close"].rename(s))

    return ["UP", "DN", "FL"], idx


def test_basket_is_bullish_in_uptrend(_stub_symbols):
    symbols, idx = _stub_symbols
    # Give only uptrend symbol so basket is monotonically rising
    regime = MarketRegime(symbols=["UP"])
    assert regime.is_bullish(idx[-1]) is True


def test_basket_is_bearish_in_downtrend(_stub_symbols):
    symbols, idx = _stub_symbols
    regime = MarketRegime(symbols=["DN"])
    assert regime.is_bullish(idx[-1]) is False


def test_permissive_before_ema_calibrated(_stub_symbols):
    """Dates before EMA50 has 50 bars → return True (permissive)."""
    symbols, idx = _stub_symbols
    regime = MarketRegime(symbols=["UP"])
    # EMA50 needs ~50 bars; date at bar 5 should still be permissive
    assert regime.is_bullish(idx[5]) is True


def test_context_returns_dict(_stub_symbols):
    symbols, idx = _stub_symbols
    regime = MarketRegime(symbols=["UP"])
    ctx = regime.context(idx[-1])
    assert ctx == {"macro_above_ema50": True}


def test_date_before_index_returns_true(_stub_symbols):
    """Date earlier than any basket data → permissive True."""
    symbols, idx = _stub_symbols
    regime = MarketRegime(symbols=["UP"])
    assert regime.is_bullish(pd.Timestamp("2000-01-01")) is True
