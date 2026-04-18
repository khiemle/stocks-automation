from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from core.data_manager import DataManager, _BATCH_DELAY, _BATCH_SIZE
from core.protocols import ValidationReport


def _make_ohlcv(n: int = 5, base_close: float = 50000.0) -> pd.DataFrame:
    idx = pd.date_range("2025-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": [base_close] * n,
            "high": [base_close * 1.02] * n,
            "low": [base_close * 0.98] * n,
            "close": [base_close] * n,
            "volume": [1_000_000] * n,
        },
        index=idx,
    )


def _mock_source(symbols_hose=None, symbols_hnx=None, ohlcv=None):
    src = MagicMock()
    src.get_universe.side_effect = lambda ex: (
        (symbols_hose or ["VCB"]) if ex == "HOSE" else (symbols_hnx or [])
    )
    src.get_daily_ohlcv.return_value = ohlcv or _make_ohlcv()
    src.get_daily_ohlcv_batch.return_value = {
        s: (ohlcv or _make_ohlcv()) for s in (symbols_hose or ["VCB"])
    }
    return src


class TestGetOhlcv:
    def test_reads_from_parquet_cache(self, tmp_path, monkeypatch):
        import core.data_manager as mod
        monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

        # Pre-write a parquet file
        parquet_dir = tmp_path / "data" / "market" / "HOSE"
        parquet_dir.mkdir(parents=True)
        df = _make_ohlcv(10)
        df.to_parquet(parquet_dir / "VCB.parquet")

        src = MagicMock()  # no network methods should be called
        dm = DataManager(src)
        result = dm.get_ohlcv("VCB", days=5)

        src.get_daily_ohlcv.assert_not_called()
        assert len(result) == 5
        assert list(result.columns) == ["open", "high", "low", "close", "volume"]

    def test_raises_if_no_file(self, tmp_path, monkeypatch):
        import core.data_manager as mod
        monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

        dm = DataManager(MagicMock())
        with pytest.raises(FileNotFoundError):
            dm.get_ohlcv("NONEXISTENT")


class TestUpdateDaily:
    def test_batches_correctly(self, tmp_path, monkeypatch):
        import core.data_manager as mod
        monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")
        monkeypatch.setattr(mod, "_BATCH_SIZE", 3)

        symbols = [f"SYM{i:02d}" for i in range(7)]
        src = _mock_source(symbols_hose=symbols, symbols_hnx=[])
        # Return today's single row per symbol
        today = date.today().isoformat()
        single_row = _make_ohlcv(1)
        src.get_daily_ohlcv_batch.return_value = {s: single_row for s in symbols}

        delays: list[float] = []
        original_sleep = time.sleep

        def capture_sleep(secs):
            delays.append(secs)

        monkeypatch.setattr(mod.time, "sleep", capture_sleep)

        dm = DataManager(src)
        status = dm.update_daily()

        # 7 symbols / batch_size 3 → 3 batches, delay called twice (not after last)
        assert src.get_daily_ohlcv_batch.call_count == 3
        assert len(delays) == 2
        assert all(d >= 2.0 for d in delays)

    def test_no_duplicate_on_re_update(self, tmp_path, monkeypatch):
        import core.data_manager as mod
        monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

        today = date.today()
        existing = _make_ohlcv(5)
        parquet_dir = tmp_path / "data" / "market" / "HOSE"
        parquet_dir.mkdir(parents=True)
        existing.to_parquet(parquet_dir / "VCB.parquet")

        today_row = pd.DataFrame(
            {"open": [62000], "high": [63000], "low": [61000], "close": [62500], "volume": [2_000_000]},
            index=pd.DatetimeIndex([pd.Timestamp(today)]),
        )
        today_row.index.name = "date"

        src = MagicMock()
        src.get_universe.side_effect = lambda ex: ["VCB"] if ex == "HOSE" else []
        src.get_daily_ohlcv_batch.return_value = {"VCB": today_row}
        monkeypatch.setattr(mod.time, "sleep", lambda _: None)

        dm = DataManager(src)
        dm.update_daily()
        dm.update_daily()  # second call — should not double-add today

        written = pd.read_parquet(parquet_dir / "VCB.parquet")
        today_rows = written[written.index.date == today]
        assert len(today_rows) == 1


class TestValidateData:
    def _write_parquet(self, tmp_path, symbol, df, exchange="HOSE"):
        d = tmp_path / "data" / "market" / exchange
        d.mkdir(parents=True, exist_ok=True)
        df.to_parquet(d / f"{symbol}.parquet")

    def test_flags_zero_volume(self, tmp_path, monkeypatch):
        import core.data_manager as mod
        monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

        df = _make_ohlcv(5)
        df.loc[df.index[2], "volume"] = 0
        self._write_parquet(tmp_path, "VCB", df)

        dm = DataManager(MagicMock())
        report = dm.validate_data("VCB", "HOSE")
        assert report.has_warnings
        assert any("volume=0" in w for w in report.warnings)

    def test_flags_price_gap(self, tmp_path, monkeypatch):
        import core.data_manager as mod
        monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

        df = _make_ohlcv(5, base_close=50000)
        # Inject a 20% gap on row 3
        df.loc[df.index[3], "close"] = 60000
        self._write_parquet(tmp_path, "VCB", df)

        dm = DataManager(MagicMock())
        report = dm.validate_data("VCB", "HOSE")
        assert report.has_warnings
        assert any("gap" in w for w in report.warnings)

    def test_flags_out_of_band_hose(self, tmp_path, monkeypatch):
        import core.data_manager as mod
        monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

        df = _make_ohlcv(5, base_close=50000)
        # Simulate high exceeding 7% band vs prev_close (+10% above prev_close=50000)
        df.loc[df.index[2], "high"] = 55000  # prev_close=50000, high=55000 → +10%
        self._write_parquet(tmp_path, "VCB", df)

        dm = DataManager(MagicMock())
        report = dm.validate_data("VCB", "HOSE")
        assert report.has_warnings
        assert any("band" in w for w in report.warnings)

    def test_no_future_data_leak(self, tmp_path, monkeypatch):
        import core.data_manager as mod
        monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

        df = _make_ohlcv(5)
        # Force a future date
        future_idx = pd.date_range("2099-01-01", periods=1, freq="B")
        future_row = pd.DataFrame(
            {"open": [99], "high": [99], "low": [99], "close": [99], "volume": [99]},
            index=future_idx,
        )
        df_with_future = pd.concat([df, future_row])
        df_with_future.index.name = "date"
        self._write_parquet(tmp_path, "VCB", df_with_future)

        dm = DataManager(MagicMock())
        report = dm.validate_data("VCB", "HOSE")
        assert report.has_warnings
        assert any("Future data" in w for w in report.warnings)

    def test_clean_data_no_warnings(self, tmp_path, monkeypatch):
        import core.data_manager as mod
        monkeypatch.setattr(mod, "_MARKET_DIR", tmp_path / "data" / "market")

        df = _make_ohlcv(10)
        self._write_parquet(tmp_path, "VCB", df)

        dm = DataManager(MagicMock())
        report = dm.validate_data("VCB", "HOSE")
        assert not report.has_warnings
