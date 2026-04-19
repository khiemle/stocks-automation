"""
Market-level regime detector for VN30 universe.

Compute equal-weight VN30 basket and its EMA50; block new BUY when basket
is trading below EMA50 (bear macro regime). This is a pre-filter applied
on top of per-symbol signals.

Used by:
- `scripts/backtest_portfolio_vn30.py` — pass market_context to evaluate()
- `core/backtester.py` — per-symbol backtest, shared basket
- `trading_bot.py` (cmd_scan) — live scan, basket computed at scan time

Single source of truth: `_MACRO_EMA_WINDOW` defined here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from ta.trend import EMAIndicator

_MACRO_EMA_WINDOW = 50  # EMA50 cho VN30 basket


def _load_vn30_symbols() -> list[str]:
    """Parse VN30 block từ data/universe/HOSE.txt."""
    path = Path("data/universe/HOSE.txt")
    symbols, in_vn30 = [], False
    for line in path.read_text().splitlines():
        s = line.strip()
        if s == "# VN30":
            in_vn30 = True
            continue
        if in_vn30:
            if s.startswith("#"):
                break
            if s:
                symbols.append(s)
    return symbols


def _load_close_series(symbol: str) -> Optional[pd.Series]:
    for exch in ("HOSE", "HNX"):
        p = Path("data/market") / exch / f"{symbol}.parquet"
        if p.exists():
            return pd.read_parquet(p)["close"].rename(symbol)
    return None


class MarketRegime:
    """
    Equal-weight VN30 basket + EMA50.

    is_bullish(date): True nếu basket close > basket EMA50 tại `date`.
    Trường hợp thiếu data (trước khi EMA50 được tính) → trả True (permissive).
    """

    def __init__(self, symbols: Optional[list[str]] = None) -> None:
        if symbols is None:
            symbols = _load_vn30_symbols()
        self._symbols = symbols
        self._basket, self._ema = self._build()

    def _build(self) -> tuple[pd.Series, pd.Series]:
        closes = []
        for s in self._symbols:
            series = _load_close_series(s)
            if series is not None:
                closes.append(series)
        if not closes:
            raise RuntimeError(f"No data loaded for symbols {self._symbols}")
        # equal-weight = mean of per-symbol normalized close;
        # we normalize to first common date to avoid big/small name bias.
        df = pd.concat(closes, axis=1)
        first_valid_per_col = df.apply(lambda c: c.first_valid_index())
        base_date = first_valid_per_col.max()
        if base_date is None:
            raise RuntimeError("No overlapping data among symbols")
        df_norm = df.divide(df.loc[base_date]).dropna(how="all")
        basket = df_norm.mean(axis=1).dropna()
        ema = EMAIndicator(basket, window=_MACRO_EMA_WINDOW).ema_indicator()
        return basket, ema

    def is_bullish(self, date) -> bool:
        try:
            ts = pd.Timestamp(date) if not isinstance(date, pd.Timestamp) else date
            if ts not in self._basket.index:
                # fall back to nearest prior date
                idx = self._basket.index.searchsorted(ts)
                if idx == 0:
                    return True
                ts = self._basket.index[idx - 1]
            b = float(self._basket.loc[ts])
            e = self._ema.loc[ts]
            if pd.isna(e):
                return True  # EMA chưa calibrated → permissive
            return b > float(e)
        except (KeyError, IndexError):
            return True

    def basket_return_20d(self, date) -> float | None:
        """Return the basket's 20-trading-day return ending at `date`. None if unavailable."""
        try:
            ts = pd.Timestamp(date) if not isinstance(date, pd.Timestamp) else date
            idx = self._basket.index.searchsorted(ts, side="right") - 1
            if idx < 20:
                return None
            prev = float(self._basket.iloc[idx - 20])
            curr = float(self._basket.iloc[idx])
            if prev <= 0:
                return None
            return curr / prev - 1.0
        except (IndexError, KeyError):
            return None

    def context(self, date) -> dict:
        """Convenience: return dict ready to pass to evaluate(market_context=...)."""
        result: dict = {"macro_above_ema50": self.is_bullish(date)}
        b_ret = self.basket_return_20d(date)
        if b_ret is not None:
            result["basket_return_20d"] = b_ret
        return result
