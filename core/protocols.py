from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, List
import pandas as pd


# ---------------------------------------------------------------------------
# Signal Engine
# ---------------------------------------------------------------------------

@dataclass
class SignalResult:
    score: float        # -1.0 → +1.0
    regime: str         # "TRENDING" | "VOLATILE" | "SIDEWAYS"
    action: str         # "BUY" | "SELL" | "HOLD"
    indicators: dict    # raw indicator values for UI display
    confidence: float   # 0.0 → 1.0


class SignalEngineProtocol(Protocol):
    name: str
    version: str

    def evaluate(
        self,
        df: pd.DataFrame,
        foreign_flow: pd.DataFrame | None,
    ) -> SignalResult: ...

    def evaluate_intraday(
        self,
        df: pd.DataFrame,
        current_price: float,
    ) -> SignalResult: ...


# ---------------------------------------------------------------------------
# Broker / Execution
# ---------------------------------------------------------------------------

@dataclass
class OrderResult:
    order_id: str
    status: str     # "PLACED" | "REJECTED" | "SIMULATED"
    message: str


@dataclass
class OrderStatus:
    order_id: str
    status: str             # "PENDING" | "FILLED" | "PARTIAL" | "CANCELLED"
    filled_qty: int
    fill_price: float | None


@dataclass
class AccountBalance:
    cash: float
    buying_power: float
    nav: float              # Net Asset Value


@dataclass
class StockPosition:
    symbol: str
    qty: int
    avg_price: float
    market_value: float


class BrokerProtocol(Protocol):
    name: str

    def place_order(
        self,
        symbol: str,
        side: str,          # "B" | "S"
        quantity: int,
        order_type: str,    # "LO" | "ATO"
        price: float | None,
        account: str,
    ) -> OrderResult: ...

    def cancel_order(self, order_id: str, account: str) -> bool: ...

    def get_order_status(self, order_id: str) -> OrderStatus: ...

    def get_account_balance(self, account: str) -> AccountBalance: ...

    def get_stock_positions(self, account: str) -> List[StockPosition]: ...


# ---------------------------------------------------------------------------
# Data Source
# ---------------------------------------------------------------------------

@dataclass
class ValidationReport:
    symbol: str
    warnings: List[str]

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


class DataSourceProtocol(Protocol):
    name: str   # "YFINANCE" | "SSI"

    def get_daily_ohlcv(
        self,
        symbol: str,
        start: str,     # ISO 8601 date "YYYY-MM-DD"
        end: str,
    ) -> pd.DataFrame:
        """Return DataFrame with columns: date, open, high, low, close, volume."""
        ...

    def get_daily_ohlcv_batch(
        self,
        symbols: List[str],
        start: str,
        end: str,
    ) -> dict[str, pd.DataFrame]:
        """Return dict symbol → DataFrame."""
        ...

    def get_intraday_price(self, symbol: str) -> float | None:
        """Return latest intraday price (delayed ~15 min for yfinance)."""
        ...

    def get_intraday_prices_batch(
        self,
        symbols: List[str],
    ) -> dict[str, float | None]:
        """Return dict symbol → latest price."""
        ...

    def get_universe(self, exchange: str) -> List[str]:
        """Return list of symbols for exchange ("HOSE" | "HNX")."""
        ...

    def get_foreign_flow(
        self,
        symbol: str,
        start: str,
        end: str,
    ) -> pd.DataFrame | None:
        """Return foreign net buy/sell DataFrame or None if unsupported."""
        ...
