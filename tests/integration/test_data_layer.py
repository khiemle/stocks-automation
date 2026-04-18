"""
Integration tests for Data Layer.
These tests hit real yfinance network — require internet.
Marked with pytest.mark.integration so they can be skipped in CI if needed.
Run: pytest tests/integration/test_data_layer.py -v
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.data_manager import DataManager
from core.trading_calendar import last_trading_date
from data_sources.yfinance_client import YFinanceClient

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# test_init_data_creates_parquet_files
# ---------------------------------------------------------------------------

def test_init_data_creates_parquet_files(tmp_path, monkeypatch):
    """init-data for 5 symbols creates correct parquet files."""
    import core.data_manager as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "market")
    monkeypatch.setattr(mod, "_BATCH_DELAY", 0)

    symbols = ["VCB", "HPG", "FPT", "MBB", "VNM"]
    src = MagicMock(spec=YFinanceClient)
    src.get_universe.side_effect = lambda ex: symbols if ex == "HOSE" else []

    end = date.today().isoformat()
    start = (date.today() - timedelta(days=365)).isoformat()

    def fake_ohlcv(sym, s, e):
        idx = pd.date_range(s, periods=10, freq="B")
        return pd.DataFrame(
            {"open": [50000]*10, "high": [51000]*10, "low": [49000]*10,
             "close": [50500]*10, "volume": [1_000_000]*10},
            index=idx,
        )

    src.get_daily_ohlcv.side_effect = fake_ohlcv

    dm = DataManager(src)
    result = dm.init_data(years=1)

    assert result.success == len(symbols)
    assert result.failed == []
    for sym in symbols:
        assert (tmp_path / "market" / "HOSE" / f"{sym}.parquet").exists()


# ---------------------------------------------------------------------------
# test_daily_update_appends_one_row
# ---------------------------------------------------------------------------

def test_daily_update_appends_one_row(tmp_path, monkeypatch):
    """update_daily appends exactly 1 new row without duplicates."""
    import core.data_manager as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "market")
    monkeypatch.setattr(mod, "_BATCH_DELAY", 0)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    # Pre-populate 5 rows of history
    parquet_dir = tmp_path / "market" / "HOSE"
    parquet_dir.mkdir(parents=True)
    hist = pd.DataFrame(
        {"open": [50000]*5, "high": [51000]*5, "low": [49000]*5,
         "close": [50500]*5, "volume": [1_000_000]*5},
        index=pd.date_range("2025-01-02", periods=5, freq="B"),
    )
    hist.to_parquet(parquet_dir / "VCB.parquet")

    today = date.today()
    today_row = pd.DataFrame(
        {"open": [51000], "high": [52000], "low": [50000],
         "close": [51500], "volume": [2_000_000]},
        index=pd.DatetimeIndex([pd.Timestamp(today)]),
    )
    today_row.index.name = "date"

    src = MagicMock()
    src.get_universe.side_effect = lambda ex: ["VCB"] if ex == "HOSE" else []
    src.get_daily_ohlcv_batch.return_value = {"VCB": today_row}

    dm = DataManager(src)
    dm.update_daily()

    written = pd.read_parquet(parquet_dir / "VCB.parquet")
    assert len(written) == 6
    assert written.index.is_monotonic_increasing
    # Run again — still 6 rows (no duplicate)
    dm.update_daily()
    written2 = pd.read_parquet(parquet_dir / "VCB.parquet")
    assert len(written2) == 6


# ---------------------------------------------------------------------------
# test_data_manager_uses_cache_not_network
# ---------------------------------------------------------------------------

def test_data_manager_uses_cache_not_network(tmp_path, monkeypatch):
    """get_ohlcv() reads from Parquet — zero network calls."""
    import core.data_manager as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "market")

    parquet_dir = tmp_path / "market" / "HOSE"
    parquet_dir.mkdir(parents=True)
    df = pd.DataFrame(
        {"open": [50000]*20, "high": [51000]*20, "low": [49000]*20,
         "close": [50500]*20, "volume": [1_000_000]*20},
        index=pd.date_range("2025-01-02", periods=20, freq="B"),
    )
    df.to_parquet(parquet_dir / "VCB.parquet")

    src = MagicMock(spec=YFinanceClient)
    dm = DataManager(src)
    result = dm.get_ohlcv("VCB", days=10)

    src.get_daily_ohlcv.assert_not_called()
    src.get_daily_ohlcv_batch.assert_not_called()
    assert len(result) == 10


# ---------------------------------------------------------------------------
# test_fetch_250_of_300_symbols_succeed  (slow — real network)
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_fetch_75pct_of_universe_succeed(tmp_path, monkeypatch):
    """Real yfinance fetch: >= 75% of universe must return data.

    Dùng last_trading_date() làm end date để tránh fetch ngày cuối tuần/
    chưa có data (trước 15:30). Threshold 75% vì HNX coverage hạn chế.
    """
    import core.data_manager as mod
    monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "market")
    monkeypatch.setattr(mod, "_BATCH_DELAY", 2.5)

    end = last_trading_date()
    start = end - timedelta(days=365)

    client = YFinanceClient()
    dm = DataManager(client)

    # Monkey-patch date.today() trong data_manager để dùng last_trading_date
    with patch("core.data_manager.date") as mock_date:
        mock_date.today.return_value = end
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = dm.init_data(years=1)

    threshold = int(result.total * 0.75)
    assert result.success >= threshold, (
        f"Only {result.success}/{result.total} succeeded (need >= {threshold}). "
        f"end={end}, Failed: {result.failed[:10]}"
    )
