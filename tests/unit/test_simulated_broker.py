from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from brokers.simulated_broker import SimulatedBroker, _COMMISSION_RATE, _SLIPPAGE_RATE


def _bar(open_price=50_000.0) -> pd.Series:
    return pd.Series({"open": open_price, "high": open_price * 1.05,
                      "low": open_price * 0.95, "close": open_price})


def _place_buy(broker, symbol="VCB", qty=100, price=None):
    return broker.place_order(symbol, "B", qty, "ATO", price, "paper")


def _place_sell(broker, symbol="VCB", qty=100):
    return broker.place_order(symbol, "S", qty, "ATO", None, "paper")


# ── SimulatedBroker tests ────────────────────────────────────────────────────

def test_buy_fills_at_next_bar_open():
    broker = SimulatedBroker(initial_cash=10_000_000)
    result = _place_buy(broker, qty=10)
    assert result.status == "PLACED"

    bar = _bar(open_price=50_000)
    broker.process_next_bar("VCB", bar, "2026-04-15")

    status = broker.get_order_status(result.order_id)
    assert status.status == "FILLED"
    expected_fill = 50_000 * (1 + _SLIPPAGE_RATE)
    assert abs(status.fill_price - expected_fill) < 1


def test_sell_fills_at_next_bar_open():
    broker = SimulatedBroker(initial_cash=10_000_000)
    _place_buy(broker, qty=10)
    broker.process_next_bar("VCB", _bar(50_000), "2026-04-10")

    # Manually back-date the buy to satisfy T+2
    broker._positions["VCB"].fill_date = "2026-04-07"

    result = _place_sell(broker, qty=10)
    broker.process_next_bar("VCB", _bar(55_000), "2026-04-11")

    status = broker.get_order_status(result.order_id)
    assert status.status == "FILLED"
    expected_fill = 55_000 * (1 - _SLIPPAGE_RATE)
    assert abs(status.fill_price - expected_fill) < 1


def test_t2_blocks_sell_within_2_business_days():
    broker = SimulatedBroker(initial_cash=10_000_000)
    buy_date = "2024-01-15"  # Monday
    _place_buy(broker, qty=10)
    broker.process_next_bar("VCB", _bar(50_000), buy_date)

    # Try to sell next day (T+1) — only 1 business day elapsed
    result = broker.place_order("VCB", "S", 10, "ATO", None, "paper", sim_date="2024-01-16")
    assert result.status == "REJECTED"
    assert "T+2" in result.message


def test_t2_allows_sell_after_2_business_days():
    broker = SimulatedBroker(initial_cash=10_000_000)
    buy_date = "2024-01-15"  # Monday
    _place_buy(broker, qty=10)
    broker.process_next_bar("VCB", _bar(50_000), buy_date)

    # Sell on Wednesday (T+2) — 2 business days elapsed
    result = broker.place_order("VCB", "S", 10, "ATO", None, "paper", sim_date="2024-01-17")
    assert result.status == "PLACED"


def test_commission_0_15pct_per_side():
    broker = SimulatedBroker(initial_cash=100_000_000)
    qty = 100
    open_price = 10_000
    _place_buy(broker, qty=qty)
    broker.process_next_bar("VCB", _bar(open_price), "2026-04-15")

    fill_price = open_price * (1 + _SLIPPAGE_RATE)
    expected_commission = qty * fill_price * _COMMISSION_RATE
    expected_cash = 100_000_000 - qty * fill_price * (1 + _COMMISSION_RATE)
    assert abs(broker._cash - expected_cash) < 1


def test_slippage_0_1pct_applied():
    broker = SimulatedBroker(initial_cash=100_000_000)
    _place_buy(broker, qty=1)
    broker.process_next_bar("VCB", _bar(40_000), "2026-04-15")
    filled = broker._filled[-1]
    assert abs(filled.fill_price - 40_000 * (1 + _SLIPPAGE_RATE)) < 0.1

    # Sell side
    broker._positions["VCB"].fill_date = "2026-04-10"
    _place_sell(broker, qty=1)
    broker.process_next_bar("VCB", _bar(42_000), "2026-04-16")
    filled = broker._filled[-1]
    assert abs(filled.fill_price - 42_000 * (1 - _SLIPPAGE_RATE)) < 0.1


def test_account_balance_decreases_on_buy():
    initial = 50_000_000
    broker = SimulatedBroker(initial_cash=initial)
    qty, open_price = 50, 20_000
    _place_buy(broker, qty=qty)
    broker.process_next_bar("VCB", _bar(open_price), "2026-04-15")

    fill = open_price * (1 + _SLIPPAGE_RATE)
    expected_cash = initial - qty * fill * (1 + _COMMISSION_RATE)
    assert abs(broker._cash - expected_cash) < 1
    assert broker._cash < initial
