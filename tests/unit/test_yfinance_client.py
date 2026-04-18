from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data_sources.yfinance_client import YFinanceClient


def _make_multi_df(symbol_suffix: str = "VCB.VN") -> pd.DataFrame:
    """Build a minimal MultiIndex DataFrame as yfinance >=0.2 returns."""
    idx = pd.to_datetime(["2025-01-02", "2025-01-03"])
    cols = pd.MultiIndex.from_tuples(
        [("Close", symbol_suffix), ("High", symbol_suffix),
         ("Low", symbol_suffix), ("Open", symbol_suffix), ("Volume", symbol_suffix)],
        names=["Price", "Ticker"],
    )
    data = [[60000, 61000, 59000, 59500, 1000000],
            [61000, 62000, 60000, 60500, 1200000]]
    return pd.DataFrame(data, index=idx, columns=cols)


def _make_single_df() -> pd.DataFrame:
    idx = pd.to_datetime(["2025-01-02", "2025-01-03"])
    df = pd.DataFrame(
        {"Open": [59500, 60500], "High": [61000, 62000],
         "Low": [59000, 60000], "Close": [60000, 61000], "Volume": [1_000_000, 1_200_000]},
        index=idx,
    )
    df.index.name = "Date"
    return df


class TestGetDailyOhlcv:
    def test_returns_correct_columns(self):
        client = YFinanceClient()
        with patch("yfinance.download", return_value=_make_multi_df()) as mock_dl:
            df = client.get_daily_ohlcv("VCB", "2025-01-01", "2025-01-31")

        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 2

    def test_vn_suffix_applied(self):
        client = YFinanceClient()
        with patch("yfinance.download", return_value=_make_multi_df()) as mock_dl:
            client.get_daily_ohlcv("VCB", "2025-01-01", "2025-01-31")
            call_args = mock_dl.call_args
            assert call_args[0][0] == "VCB.VN"

    def test_index_name_is_date(self):
        client = YFinanceClient()
        with patch("yfinance.download", return_value=_make_multi_df()):
            df = client.get_daily_ohlcv("VCB", "2025-01-01", "2025-01-31")
        assert df.index.name == "date"

    def test_sorted_ascending(self):
        client = YFinanceClient()
        with patch("yfinance.download", return_value=_make_multi_df()):
            df = client.get_daily_ohlcv("VCB", "2025-01-01", "2025-01-31")
        assert df.index.is_monotonic_increasing


class TestGetDailyOhlcvBatch:
    def _make_batch_df(self, symbols):
        frames = {}
        for sym in symbols:
            frames[sym + ".VN"] = _make_multi_df(sym + ".VN")
        # Simulate yfinance multi-ticker MultiIndex
        combined = pd.concat(frames, axis=1)
        combined.columns.names = ["Price", "Ticker"]  # already correct
        return combined

    def test_batch_returns_all_symbols(self):
        client = YFinanceClient()
        symbols = ["VCB", "HPG", "FPT"]

        # yfinance group_by="ticker" → first level is Ticker, second is Price
        idx = pd.to_datetime(["2025-01-02", "2025-01-03"])
        tuples = []
        for s in symbols:
            for col in ("Close", "High", "Low", "Open", "Volume"):
                tuples.append((s + ".VN", col))
        cols = pd.MultiIndex.from_tuples(tuples, names=["Ticker", "Price"])
        data = [[60000] * len(tuples)] * 2
        mock_df = pd.DataFrame(data, index=idx, columns=cols)

        with patch("yfinance.download", return_value=mock_df):
            result = client.get_daily_ohlcv_batch(symbols, "2025-01-01", "2025-01-31")

        assert set(result.keys()) == set(symbols)
        for sym, df in result.items():
            assert list(df.columns) == ["open", "high", "low", "close", "volume"]


class TestGetForeignFlow:
    def test_returns_none(self):
        client = YFinanceClient()
        result = client.get_foreign_flow("VCB", "2025-01-01", "2025-01-31")
        assert result is None

    def test_does_not_crash(self):
        client = YFinanceClient()
        # Should never raise regardless of symbol
        try:
            client.get_foreign_flow("ANYTHING", "2025-01-01", "2025-01-31")
        except Exception:
            pytest.fail("get_foreign_flow should not raise")


class TestGetUniverse:
    def test_reads_from_hose_file(self, tmp_path, monkeypatch):
        universe_dir = tmp_path / "data" / "universe"
        universe_dir.mkdir(parents=True)
        (universe_dir / "HOSE.txt").write_text("# comment\nVCB\nHPG\nFPT\n")

        import data_sources.yfinance_client as mod
        monkeypatch.setattr(mod, "_UNIVERSE_DIR", universe_dir)

        client = YFinanceClient()
        symbols = client.get_universe("HOSE")
        assert symbols == ["VCB", "HPG", "FPT"]

    def test_skips_comments_and_blank_lines(self, tmp_path, monkeypatch):
        universe_dir = tmp_path / "data" / "universe"
        universe_dir.mkdir(parents=True)
        (universe_dir / "HNX.txt").write_text("# header\n\nSHB\n\nCEO\n")

        import data_sources.yfinance_client as mod
        monkeypatch.setattr(mod, "_UNIVERSE_DIR", universe_dir)

        client = YFinanceClient()
        symbols = client.get_universe("HNX")
        assert symbols == ["SHB", "CEO"]

    def test_missing_file_raises(self, tmp_path, monkeypatch):
        import data_sources.yfinance_client as mod
        monkeypatch.setattr(mod, "_UNIVERSE_DIR", tmp_path)

        client = YFinanceClient()
        with pytest.raises(FileNotFoundError):
            client.get_universe("HOSE")
