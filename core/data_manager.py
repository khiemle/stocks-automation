from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import List

import pandas as pd

from core.protocols import DataSourceProtocol, ValidationReport

logger = logging.getLogger(__name__)

_MARKET_DIR = Path("data/market")
_BATCH_SIZE = 50
_BATCH_DELAY = 2.5      # seconds between batches
_HISTORY_YEARS = 5
_HOSE_BAND = 0.07
_HNX_BAND = 0.10
_GAP_THRESHOLD = 0.15


@dataclass
class InitDataResult:
    total: int
    success: int
    failed: List[str] = field(default_factory=list)


class DataManager:
    def __init__(self, data_source: DataSourceProtocol) -> None:
        self._src = data_source

    # ------------------------------------------------------------------
    # Public read interface (hot path — reads from local Parquet)
    # ------------------------------------------------------------------

    def get_ohlcv(self, symbol: str, days: int = 120) -> pd.DataFrame:
        """Load last `days` rows from Parquet cache. No network call."""
        path = self._parquet_path(symbol)
        if not path.exists():
            raise FileNotFoundError(f"No data for {symbol}. Run init-data first.")
        df = pd.read_parquet(path)
        return df.tail(days)

    def get_universe(self, exchange: str) -> List[str]:
        return self._src.get_universe(exchange)

    # ------------------------------------------------------------------
    # Initial data load
    # ------------------------------------------------------------------

    def init_data(self, years: int = _HISTORY_YEARS) -> InitDataResult:
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=years * 365)).isoformat()

        symbols_hose = self._src.get_universe("HOSE")
        symbols_hnx = self._src.get_universe("HNX")
        all_symbols = [(s, "HOSE") for s in symbols_hose] + [(s, "HNX") for s in symbols_hnx]

        logger.info("init_data: %d symbols, %s → %s", len(all_symbols), start, end)

        result = InitDataResult(total=len(all_symbols), success=0)
        batches = [all_symbols[i: i + _BATCH_SIZE] for i in range(0, len(all_symbols), _BATCH_SIZE)]

        for idx, batch in enumerate(batches, 1):
            logger.info("Batch %d/%d (%d symbols)", idx, len(batches), len(batch))
            for symbol, exchange in batch:
                try:
                    df = self._src.get_daily_ohlcv(symbol, start, end)
                    if not df.empty:
                        self._write_parquet(symbol, exchange, df)
                        result.success += 1
                    else:
                        logger.warning("Empty data for %s", symbol)
                        result.failed.append(symbol)
                except Exception as exc:
                    logger.error("init_data failed for %s: %s", symbol, exc)
                    result.failed.append(symbol)
            if idx < len(batches):
                time.sleep(_BATCH_DELAY)

        logger.info(
            "init_data done: %d/%d success, %d failed",
            result.success, result.total, len(result.failed),
        )
        return result

    # ------------------------------------------------------------------
    # Daily update (called at 15:35)
    # ------------------------------------------------------------------

    def update_daily(self) -> dict[str, bool]:
        today = date.today().isoformat()
        symbols_hose = self._src.get_universe("HOSE")
        symbols_hnx = self._src.get_universe("HNX")
        all_symbols = [(s, "HOSE") for s in symbols_hose] + [(s, "HNX") for s in symbols_hnx]

        logger.info("update_daily: %d symbols for %s", len(all_symbols), today)

        status: dict[str, bool] = {}
        batches = [all_symbols[i: i + _BATCH_SIZE] for i in range(0, len(all_symbols), _BATCH_SIZE)]

        for idx, batch in enumerate(batches, 1):
            syms = [s for s, _ in batch]
            exchange_map = {s: e for s, e in batch}
            try:
                new_data = self._src.get_daily_ohlcv_batch(syms, today, today)
            except Exception as exc:
                logger.error("Batch %d fetch failed: %s", idx, exc)
                for s in syms:
                    status[s] = False
                continue

            for symbol in syms:
                df_new = new_data.get(symbol)
                if df_new is None or df_new.empty:
                    logger.warning("No data today for %s", symbol)
                    status[symbol] = False
                    continue
                try:
                    path = self._parquet_path(symbol)
                    if path.exists():
                        df_old = pd.read_parquet(path)
                        # Drop any existing rows for today to avoid duplicates
                        df_old = df_old[df_old.index < pd.Timestamp(today)]
                        df = pd.concat([df_old, df_new]).sort_index()
                    else:
                        df = df_new
                    self._write_parquet(symbol, exchange_map[symbol], df)
                    status[symbol] = True
                except Exception as exc:
                    logger.error("update_daily write failed for %s: %s", symbol, exc)
                    status[symbol] = False

            if idx < len(batches):
                time.sleep(_BATCH_DELAY)

        return status

    # ------------------------------------------------------------------
    # Data quality validation
    # ------------------------------------------------------------------

    def validate_data(self, symbol: str, exchange: str = "HOSE") -> ValidationReport:
        warnings: List[str] = []
        path = self._parquet_path(symbol)
        if not path.exists():
            return ValidationReport(symbol=symbol, warnings=[f"No parquet file for {symbol}"])

        df = pd.read_parquet(path)

        # No future data leak
        today = pd.Timestamp(date.today())
        if df.index.max() > today:
            warnings.append(f"Future data detected: max date {df.index.max().date()} > today {today.date()}")

        # Zero volume days (trading days only — rough check)
        zero_vol = df[df["volume"] == 0]
        if not zero_vol.empty:
            warnings.append(f"{len(zero_vol)} rows with volume=0")

        # Price gaps > threshold (close-to-close; may be triggered by dividend adjustment)
        band = _HNX_BAND if exchange == "HNX" else _HOSE_BAND
        pct_change = df["close"].pct_change().abs()
        gap_days = pct_change[pct_change > _GAP_THRESHOLD]
        if not gap_days.empty:
            warnings.append(f"{len(gap_days)} days with close gap > {_GAP_THRESHOLD:.0%}")

        # Price band: use intraday range (high/low vs open) — not close-to-close
        # close-to-close triggers false positives on dividend ex-dates (adjusted prices)
        if "open" in df.columns:
            intraday_up = (df["high"] - df["open"]) / df["open"]
            intraday_dn = (df["open"] - df["low"]) / df["open"]
            intraday_max = pd.concat([intraday_up, intraday_dn], axis=1).max(axis=1)
            out_of_band = intraday_max[intraday_max > band]
            if not out_of_band.empty:
                warnings.append(
                    f"{len(out_of_band)} days with intraday range > {band:.0%} (price band)"
                )

        return ValidationReport(symbol=symbol, warnings=warnings)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parquet_path(symbol: str) -> Path:
        # Infer exchange from universe files lazily; default subdir by first lookup
        for exchange in ("HOSE", "HNX"):
            path = _MARKET_DIR / exchange / f"{symbol}.parquet"
            if path.exists():
                return path
        # Default to HOSE for new writes — caller should use _write_parquet directly
        return _MARKET_DIR / "HOSE" / f"{symbol}.parquet"

    @staticmethod
    def _write_parquet(symbol: str, exchange: str, df: pd.DataFrame) -> None:
        path = _MARKET_DIR / exchange / f"{symbol}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, engine="pyarrow", compression="snappy")
