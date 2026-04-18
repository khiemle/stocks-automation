from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_UNIVERSE_DIR = Path("data/universe")
_VN_SUFFIX = ".VN"


def _ticker(symbol: str) -> str:
    return symbol + _VN_SUFFIX


class YFinanceClient:
    name = "YFINANCE"

    # ------------------------------------------------------------------
    # Daily OHLCV
    # ------------------------------------------------------------------

    def get_daily_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        df = yf.download(
            _ticker(symbol),
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
        )
        return self._normalise(df, symbol)

    def get_daily_ohlcv_batch(
        self, symbols: List[str], start: str, end: str
    ) -> dict[str, pd.DataFrame]:
        tickers = [_ticker(s) for s in symbols]
        raw = yf.download(
            tickers,
            start=start,
            end=end,
            auto_adjust=True,
            group_by="ticker",
            progress=False,
        )
        result: dict[str, pd.DataFrame] = {}
        for symbol, ticker in zip(symbols, tickers):
            try:
                if len(symbols) == 1:
                    df = raw
                else:
                    df = raw[ticker]
                result[symbol] = self._normalise(df, symbol)
            except Exception as exc:
                logger.warning("yfinance batch failed for %s: %s", symbol, exc)
        return result

    # ------------------------------------------------------------------
    # Intraday (delayed ~15 min)
    # ------------------------------------------------------------------

    def get_intraday_price(self, symbol: str) -> float | None:
        try:
            info = yf.Ticker(_ticker(symbol)).fast_info
            price = info.last_price
            return float(price) if price else None
        except Exception as exc:
            logger.warning("intraday price failed for %s: %s", symbol, exc)
            return None

    def get_intraday_prices_batch(
        self, symbols: List[str]
    ) -> dict[str, float | None]:
        return {s: self.get_intraday_price(s) for s in symbols}

    # ------------------------------------------------------------------
    # Universe
    # ------------------------------------------------------------------

    def get_universe(self, exchange: str) -> List[str]:
        path = _UNIVERSE_DIR / f"{exchange}.txt"
        if not path.exists():
            raise FileNotFoundError(f"Universe file not found: {path}")
        symbols = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                symbols.append(line)
        return symbols

    # ------------------------------------------------------------------
    # Foreign flow — not supported by yfinance
    # ------------------------------------------------------------------

    def get_foreign_flow(
        self, symbol: str, start: str, end: str
    ) -> pd.DataFrame | None:
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = df.copy()
        # yfinance >=0.2.x returns MultiIndex (Price, Ticker); flatten it
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [price.lower() for price, _ticker in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                raise ValueError(f"Missing column '{col}' for {symbol}")
        return df[["open", "high", "low", "close", "volume"]].sort_index()
