from __future__ import annotations

from datetime import date

import pytest

from core.risk_engine import RiskEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine(backtest_mdd: float = 0.10, capital: float = 500_000_000) -> RiskEngine:
    return RiskEngine(backtest_mdd=backtest_mdd, capital=capital)


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------

def test_position_size_2pct_risk():
    """capital=500M, close=50k, ATR=1500 → correct stop/TP + size bounded by 20% cap."""
    eng = _engine(capital=500_000_000)
    close = 50_000.0
    atr = 1_500.0
    result = eng.compute_position_size(close, atr)

    stop_distance = atr * 1.5  # 2250

    # Verify stop and TP prices
    assert result.stop_price == pytest.approx(close - stop_distance)
    assert result.take_profit == pytest.approx(close + atr * 4.5)
    assert result.stop_distance == pytest.approx(stop_distance)

    # 2% risk → 4444 raw shares; 20% cap → 2000 shares (binding constraint)
    max_2pct = int(500_000_000 * 0.02 / stop_distance)   # 4444
    max_20pct = int(500_000_000 * 0.20 / close)           # 2000
    expected = (min(max_2pct, max_20pct) // 100) * 100    # 2000
    assert result.shares == expected
    assert result.eligible


def test_max_position_cap_at_20pct():
    """If 2% risk would exceed 20% of capital, cap at 20%."""
    # Very large ATR → risk sizing gives huge number; 20% cap kicks in
    eng = _engine(capital=500_000_000)
    close = 10_000.0
    atr = 100.0  # tiny ATR → stop_distance = 150 → 10M / 150 ≈ 66666 shares @ 10k = 666M > 20%
    result = eng.compute_position_size(close, atr)

    max_by_capital = int(500_000_000 * 0.20 / close)  # 10000 shares
    max_by_capital_rounded = (max_by_capital // 100) * 100

    assert result.shares <= max_by_capital_rounded
    assert result.eligible


def test_order_size_max_5pct_adv():
    """ADV=5000 shares → 5% cap = 250 → rounded 200, warning emitted."""
    eng = _engine(capital=500_000_000)
    close = 50_000.0
    atr = 500.0       # stop_distance=750, within HOSE band (stop=49250>46500)
    adv = 5_000       # 5% = 250 → lot-rounded = 200

    result = eng.compute_position_size(close, atr, adv=adv)
    max_by_adv = (int(adv * 0.05) // 100) * 100  # 200

    assert result.shares == max_by_adv
    assert any("ADV" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Stop loss & price band
# ---------------------------------------------------------------------------

def test_stop_loss_check_hose_price_band():
    """stop < close×0.93 (HOSE ±7%) → not eligible, warning issued."""
    eng = _engine()
    close = 50_000.0
    # ATR=4000 → stop = 50000 - 6000 = 44000 < 50000*0.93=46500
    atr = 4_000.0
    result = eng.compute_position_size(close, atr, exchange="HOSE")
    assert not result.eligible
    assert result.shares == 0
    assert len(result.warnings) > 0


def test_stop_loss_check_hnx_price_band():
    """stop < close×0.90 (HNX ±10%) → not eligible, warning issued."""
    eng = _engine()
    close = 50_000.0
    # ATR=4000 → stop=44000 < 50000*0.90=45000
    atr = 4_000.0
    result = eng.compute_position_size(close, atr, exchange="HNX")
    assert not result.eligible
    assert result.shares == 0


def test_stop_price_within_hose_band_is_eligible():
    """Small ATR → stop within ±7% → eligible."""
    eng = _engine()
    close = 50_000.0
    atr = 1_000.0  # stop = 50000 - 1500 = 48500 > 46500
    result = eng.compute_position_size(close, atr, exchange="HOSE")
    assert result.eligible


# ---------------------------------------------------------------------------
# T+2 enforcement
# ---------------------------------------------------------------------------

def test_t2_enforcement_blocks_sell():
    """Buy Monday → sell Tuesday = 1 bday → blocked (False)."""
    buy = date(2026, 4, 13)   # Monday
    sell = date(2026, 4, 14)  # Tuesday
    assert not RiskEngine.check_t2(buy, sell)


def test_t2_enforcement_allows_sell_on_t2():
    """Buy Monday → sell Wednesday = 2 bdays → allowed (True)."""
    buy = date(2026, 4, 13)   # Monday
    sell = date(2026, 4, 15)  # Wednesday
    assert RiskEngine.check_t2(buy, sell)


def test_t2_enforcement_skips_weekend():
    """Buy Friday → sell Monday = 1 bday (weekend skipped) → blocked."""
    buy = date(2026, 4, 17)   # Friday
    sell = date(2026, 4, 20)  # Monday
    assert not RiskEngine.check_t2(buy, sell)


def test_t2_enforcement_buy_friday_sell_tuesday():
    """Buy Friday → sell Tuesday = 2 bdays → allowed."""
    buy = date(2026, 4, 17)   # Friday
    sell = date(2026, 4, 21)  # Tuesday
    assert RiskEngine.check_t2(buy, sell)


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

def test_circuit_breaker_triggers_at_150pct():
    """real_MDD = 1.6× backtest → stop_all() triggered."""
    eng = _engine(backtest_mdd=0.10)
    triggered = eng.check_circuit_breaker(current_mdd=0.16)  # 1.6× 0.10
    assert triggered
    assert not eng.is_new_position_allowed()


def test_circuit_breaker_no_trigger_below_150pct():
    """real_MDD = 1.4× backtest → no trigger."""
    eng = _engine(backtest_mdd=0.10)
    triggered = eng.check_circuit_breaker(current_mdd=0.14)  # 1.4× 0.10
    assert not triggered
    assert eng.is_new_position_allowed()


# ---------------------------------------------------------------------------
# Trailing stop constants
# ---------------------------------------------------------------------------

def test_trailing_stop_constants_match_spec():
    """Doc cam kết trigger = 1R (1.5×ATR) và trail distance = 2×ATR."""
    assert RiskEngine.ATR_TRAIL_TRIGGER == RiskEngine.ATR_STOP_MULT  # 1R = stop distance
    assert RiskEngine.ATR_TRAIL_MULT == 2.0


def test_trailing_stop_update_ratchets_monotonically():
    """trailing_stop_update chỉ tăng, không giảm."""
    s1 = RiskEngine._engine().trailing_stop_update if hasattr(RiskEngine, "_engine") else None
    eng = _engine()
    # current=47, price goes up → new stop increases
    s1 = eng.trailing_stop_update(current_stop=47_000, current_price=50_000, atr=1_000)
    assert s1 >= 47_000
    # price then drops → new stop must not decrease below s1
    s2 = eng.trailing_stop_update(current_stop=s1, current_price=49_000, atr=1_000)
    assert s2 == s1


# ---------------------------------------------------------------------------
# Weekly loss limits
# ---------------------------------------------------------------------------

def test_weekly_loss_limit_warning_at_1_5pct():
    """weekly PnL = -1.6% → WARN."""
    eng = _engine(capital=100_000_000)
    eng.reset_week(100_000_000)
    status = eng.check_weekly_loss(98_400_000)  # -1.6%
    assert status == "WARN"
    assert eng.is_new_position_allowed()  # WARN doesn't stop


def test_weekly_loss_limit_stop_at_3pct():
    """weekly PnL = -3.1% → STOP, no new positions."""
    eng = _engine(capital=100_000_000)
    eng.reset_week(100_000_000)
    status = eng.check_weekly_loss(96_900_000)  # -3.1%
    assert status == "STOP"
    assert not eng.is_new_position_allowed()


def test_weekly_loss_limit_ok_below_warn():
    """weekly PnL = -1.0% → OK."""
    eng = _engine(capital=100_000_000)
    eng.reset_week(100_000_000)
    status = eng.check_weekly_loss(99_000_000)  # -1.0%
    assert status == "OK"
