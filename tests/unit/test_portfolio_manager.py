from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from core.portfolio_manager import (
    PortfolioManager,
    Position,
    TradeRecord,
    _COMMISSION_RATE,
    _SLIPPAGE_RATE,
)


def _make_pm(tmp_path, cash=500_000_000):
    return PortfolioManager(
        initial_cash=cash,
        db_path=tmp_path / "trades.db",
        portfolio_path=tmp_path / "portfolio.json",
    )


def _pos(symbol="VCB", qty=100, avg_price=50_000.0, stop=46_000.0, tp=68_000.0):
    return Position(
        symbol=symbol,
        qty=qty,
        avg_price=avg_price,
        stop_loss=stop,
        take_profit=tp,
        buy_date=date.today().isoformat(),
    )


class TestRealizedPnL:
    def test_realized_pnl_includes_commission_and_slippage(self, tmp_path):
        pm = _make_pm(tmp_path)
        pm.open_position(_pos("VCB", qty=100, avg_price=50_000))
        trade = pm.close_position("VCB", exit_price=53_000)

        assert trade is not None
        gross = 100 * (53_000 - 50_000)           # 300_000
        commission = 100 * (50_000 + 53_000) * _COMMISSION_RATE
        slippage   = 100 * (50_000 + 53_000) * _SLIPPAGE_RATE
        expected_net = gross - commission - slippage

        assert abs(trade.gross_pnl - gross) < 1
        assert abs(trade.commission - commission) < 1
        assert abs(trade.slippage - slippage) < 1
        assert abs(trade.net_pnl - expected_net) < 1


class TestUnrealizedPnL:
    def test_unrealized_pnl_uses_current_price(self, tmp_path):
        pm = _make_pm(tmp_path)
        pm.open_position(_pos("VCB", qty=200, avg_price=50_000))

        prices = {"VCB": 53_000.0}
        unrealized = pm.get_unrealized_pnl(prices)

        gross = 200 * (53_000 - 50_000)
        buy_cost  = 200 * 50_000 * (_COMMISSION_RATE + _SLIPPAGE_RATE)
        sell_cost = 200 * 53_000 * (_COMMISSION_RATE + _SLIPPAGE_RATE)
        expected = gross - buy_cost - sell_cost

        assert abs(unrealized - expected) < 1


class TestTotalEquity:
    def test_total_equity_is_cash_plus_market_value(self, tmp_path):
        initial = 500_000_000
        pm = _make_pm(tmp_path, cash=initial)
        pm.open_position(_pos("VCB", qty=100, avg_price=50_000))

        prices = {"VCB": 52_000.0}
        equity = pm.get_equity(prices)
        mv = pm.get_market_value(prices)

        assert abs(equity - (pm.cash + mv)) < 1
        assert equity > 0


class TestWinRate:
    def test_win_rate_calculation(self, tmp_path):
        pm = _make_pm(tmp_path)
        # 6 wins: open and close each at a profit
        for i in range(6):
            sym = f"W{i:02d}"
            pm.open_position(_pos(sym, qty=10, avg_price=10_000))
            pm.close_position(sym, exit_price=11_000)

        # 4 losses
        for i in range(4):
            sym = f"L{i:02d}"
            pm.open_position(_pos(sym, qty=10, avg_price=10_000))
            pm.close_position(sym, exit_price=9_000)

        assert abs(pm.win_rate() - 0.60) < 1e-9


class TestProfitFactor:
    def test_profit_factor(self, tmp_path):
        pm = _make_pm(tmp_path, cash=1_000_000_000)
        # 3 wins summing to ~15M net
        for _ in range(3):
            pm.open_position(_pos("VCB", qty=1000, avg_price=50_000))
            pm.close_position("VCB", exit_price=55_000)

        # 2 losses summing to ~8M net
        for _ in range(2):
            pm.open_position(_pos("VCB", qty=1000, avg_price=50_000))
            pm.close_position("VCB", exit_price=46_000)

        wins   = sum(t.net_pnl for t in pm.trades if t.net_pnl > 0)
        losses = abs(sum(t.net_pnl for t in pm.trades if t.net_pnl < 0))
        expected_pf = wins / losses

        assert abs(pm.profit_factor() - expected_pf) < 1e-6


class TestMDD:
    def test_mdd_calculation(self, tmp_path):
        pm = _make_pm(tmp_path)
        # equity: 100 → 120 → 90 → 110
        # peak=120, trough=90 → MDD = 30/120 = 25%
        curve = [100, 120, 90, 110]
        mdd = pm.max_drawdown(curve)
        assert abs(mdd - 0.25) < 1e-9

    def test_mdd_monotonic_rise_is_zero(self, tmp_path):
        pm = _make_pm(tmp_path)
        assert pm.max_drawdown([100, 110, 120, 130]) == 0.0


class TestSharpeRatio:
    def test_sharpe_ratio_positive_for_stable_curve(self, tmp_path):
        pm = _make_pm(tmp_path)
        # Stable upward curve → positive Sharpe
        curve = [100_000 * (1 + 0.001 * i) for i in range(60)]
        sharpe = pm.sharpe_ratio(curve)
        assert sharpe > 0


class TestWeeklyPnL:
    def test_weekly_pnl_resets_on_monday(self, tmp_path, monkeypatch):
        pm = _make_pm(tmp_path, cash=100_000_000)
        import core.portfolio_manager as mod

        # Simulate equity growing mid-week
        pm._equity_week_start = 100_000_000
        pm._week_start_date = "2026-04-13"  # Monday

        # Force "today" to appear as a new Monday
        import pandas as pd

        class FakeDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 4, 20)  # next Monday

        monkeypatch.setattr(mod, "date", FakeDate)

        # Call weekly_pnl_pct; should reset equity_week_start to current equity
        current_equity = 105_000_000
        pct = pm.weekly_pnl_pct(current_equity)

        # After reset, week_start == current_equity → pct == 0
        assert abs(pct) < 1e-9
        assert pm._week_start_date == "2026-04-20"


class TestSQLitePersistence:
    def test_trade_written_to_sqlite_with_all_fields(self, tmp_path):
        pm = _make_pm(tmp_path)
        pm.open_position(_pos("HPG", qty=500, avg_price=30_000))
        pm.close_position("HPG", exit_price=33_000, exit_date="2026-04-18")

        with sqlite3.connect(tmp_path / "trades.db") as conn:
            cols = [d[1] for d in conn.execute("PRAGMA table_info(trades)").fetchall()]
            row = conn.execute("SELECT * FROM trades WHERE symbol='HPG'").fetchone()

        assert row is not None
        row_dict = dict(zip(cols, row))
        assert row_dict["symbol"] == "HPG"
        assert row_dict["quantity"] == 500
        assert row_dict["entry_price"] == 30_000
        assert row_dict["exit_price"] == 33_000
        assert row_dict["net_pnl"] != 0
        assert row_dict["closed_at"] != ""

    def test_no_duplicate_trade_on_double_close(self, tmp_path):
        pm = _make_pm(tmp_path)
        pm.open_position(_pos("VCB", qty=100, avg_price=50_000))
        pm.close_position("VCB", exit_price=52_000)
        pm.close_position("VCB", exit_price=52_000)  # second call — no-op

        with sqlite3.connect(tmp_path / "trades.db") as conn:
            count = conn.execute("SELECT COUNT(*) FROM trades WHERE symbol='VCB'").fetchone()[0]

        assert count == 1
        assert len(pm.trades) == 1


class TestStatePersistence:
    def test_portfolio_state_survives_restart(self, tmp_path):
        pm = _make_pm(tmp_path, cash=300_000_000)
        pm.open_position(_pos("VNM", qty=200, avg_price=80_000))
        pm.save_state()

        pm2 = PortfolioManager(
            initial_cash=999,  # ignored — loaded from JSON
            db_path=tmp_path / "trades.db",
            portfolio_path=tmp_path / "portfolio.json",
        )

        assert abs(pm2.cash - pm.cash) < 1
        assert "VNM" in pm2.positions
        assert pm2.positions["VNM"].qty == 200
        assert abs(pm2.positions["VNM"].avg_price - 80_000) < 1
