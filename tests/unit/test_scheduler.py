"""Unit tests for TradingBot APScheduler setup (Week 6)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _make_bot(tmp_path: Path):
    import core.bot as bot_module
    import core.portfolio_manager as pm_module

    bot_module._SIGNAL_QUEUE_PATH = tmp_path / "signal_queue.json"
    pm_module._DEFAULT_DB_PATH = tmp_path / "trades.db"
    pm_module._DEFAULT_PORTFOLIO_PATH = tmp_path / "portfolio.json"

    from core.bot import TradingBot

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal_engines": [{"name": "MomentumV1", "enabled": True, "weight": 1.0}],
        "signal": {"min_score": 0.55},
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
    dm = MagicMock()
    dm.get_universe.return_value = []
    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()
    engine = MagicMock()
    engine.name = "MomentumV1"
    return TradingBot(config=config, data_manager=dm, signal_engines=[engine], broker=broker)


def test_scheduler_starts_and_stops(tmp_path):
    """bot.start() → scheduler running=True; bot.stop() → running=False."""
    bot = _make_bot(tmp_path)
    bot.start()
    try:
        assert bot.scheduler is not None
        assert bot.scheduler.running
    finally:
        bot.stop()
    assert not bot.scheduler.running


def test_scheduler_registers_all_jobs(tmp_path):
    """start() → 7 jobs registered (daily, order, cancel, equity, weekly, expiry, intraday)."""
    bot = _make_bot(tmp_path)
    bot.start()
    try:
        job_ids = {job.id for job in bot.scheduler.get_jobs()}
        expected = {
            "daily_scan", "order_placement", "cancel_unfilled",
            "equity_snapshot", "weekly_reset", "signal_expiry",
            "intraday_monitor",
        }
        assert expected == job_ids
    finally:
        bot.stop()


def test_scheduler_timezone_is_vietnam(tmp_path):
    """Scheduler phải dùng timezone Asia/Ho_Chi_Minh."""
    bot = _make_bot(tmp_path)
    bot.start()
    try:
        # APScheduler 3.x stores timezone on scheduler object
        tz_str = str(bot.scheduler.timezone)
        assert "Ho_Chi_Minh" in tz_str or "Asia/" in tz_str
    finally:
        bot.stop()
