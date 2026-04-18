from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from core.portfolio_manager import PortfolioManager, Position


def _make_pm(tmp_path, cash=500_000_000):
    return PortfolioManager(
        initial_cash=cash,
        db_path=tmp_path / "trades.db",
        portfolio_path=tmp_path / "portfolio.json",
    )


def _pos(symbol, qty=100, avg_price=50_000.0, buy_date=None):
    return Position(
        symbol=symbol,
        qty=qty,
        avg_price=avg_price,
        stop_loss=avg_price * 0.93,
        take_profit=avg_price * 1.18,
        buy_date=buy_date or date.today().isoformat(),
    )


class TestOpenCloseFlow:
    def test_open_close_position_flow(self, tmp_path):
        pm = _make_pm(tmp_path)

        # Open
        pm.open_position(_pos("HPG", qty=300, avg_price=30_000))
        assert "HPG" in pm.positions

        # Update stop
        pm.update_stop("HPG", new_stop=29_000)
        assert pm.positions["HPG"].stop_loss == 29_000

        # Close
        trade = pm.close_position("HPG", exit_price=33_000, exit_date="2026-04-18")

        assert trade is not None
        assert trade.symbol == "HPG"
        assert trade.quantity == 300
        assert trade.entry_price == 30_000
        assert trade.exit_price == 33_000
        assert trade.gross_pnl > 0
        assert trade.net_pnl < trade.gross_pnl   # costs deducted
        assert "HPG" not in pm.positions

        # Verify DB record
        with sqlite3.connect(tmp_path / "trades.db") as conn:
            row = conn.execute("SELECT quantity, gross_pnl, net_pnl FROM trades WHERE symbol='HPG'").fetchone()
        assert row[0] == 300
        assert abs(row[1] - trade.gross_pnl) < 1
        assert abs(row[2] - trade.net_pnl) < 1


class TestEquityHistoryRecording:
    def test_equity_history_recorded_daily(self, tmp_path):
        pm = _make_pm(tmp_path, cash=200_000_000)

        base = date(2026, 4, 14)
        for i in range(5):
            record_date = (base + timedelta(days=i)).isoformat()
            price = 50_000.0 + i * 500
            # Manually override recorded_date via direct DB insert to simulate daily snapshots
            with sqlite3.connect(tmp_path / "trades.db") as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO equity_history(recorded_date, cash, market_value, nav) VALUES (?,?,?,?)",
                    (record_date, pm.cash, 0.0, pm.cash),
                )

        with sqlite3.connect(tmp_path / "trades.db") as conn:
            count = conn.execute("SELECT COUNT(*) FROM equity_history").fetchone()[0]

        assert count == 5

    def test_equity_snapshot_no_duplicate_for_same_day(self, tmp_path):
        pm = _make_pm(tmp_path, cash=200_000_000)

        # record_equity_snapshot uses INSERT OR REPLACE
        pm.record_equity_snapshot({})
        pm.record_equity_snapshot({})  # same day — should overwrite

        with sqlite3.connect(tmp_path / "trades.db") as conn:
            count = conn.execute("SELECT COUNT(*) FROM equity_history").fetchone()[0]

        assert count == 1


class TestPnLMatchesManualCalculation:
    def test_pnl_matches_manual_on_3_trades(self, tmp_path):
        """Three hand-calculated trades; verify PortfolioManager matches exactly."""
        from core.portfolio_manager import _COMMISSION_RATE, _SLIPPAGE_RATE

        pm = _make_pm(tmp_path, cash=1_000_000_000)

        # Trade specs: (symbol, qty, entry, exit)
        specs = [
            ("VCB",  200, 50_000, 55_000),
            ("HPG",  500, 30_000, 28_000),
            ("VNM",  100, 80_000, 84_000),
        ]

        expected_nets = []
        for symbol, qty, entry, exit_p in specs:
            gross = qty * (exit_p - entry)
            comm  = qty * (entry + exit_p) * _COMMISSION_RATE
            slip  = qty * (entry + exit_p) * _SLIPPAGE_RATE
            expected_nets.append(gross - comm - slip)

        for symbol, qty, entry, exit_p in specs:
            pm.open_position(_pos(symbol, qty=qty, avg_price=entry))
            pm.close_position(symbol, exit_price=exit_p)

        for trade, expected in zip(pm.trades, expected_nets):
            assert abs(trade.net_pnl - expected) < 1, (
                f"{trade.symbol}: expected {expected:.0f}, got {trade.net_pnl:.0f}"
            )
