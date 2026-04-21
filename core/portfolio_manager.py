from __future__ import annotations

import json
import logging
import math
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

from brokers.simulated_broker import _COMMISSION_RATE, _SLIPPAGE_RATE  # single source of truth
_TOTAL_COST_RATE = (_COMMISSION_RATE + _SLIPPAGE_RATE) * 2  # both sides

_DEFAULT_DB_PATH        = Path("data/trades.db")
_DEFAULT_PORTFOLIO_PATH = Path("data/portfolio.json")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT    NOT NULL,
    side          TEXT    NOT NULL,    -- 'BUY' | 'SELL'
    quantity      INTEGER NOT NULL,
    entry_price   REAL    NOT NULL,
    exit_price    REAL    NOT NULL,
    entry_date    TEXT    NOT NULL,    -- ISO date
    exit_date     TEXT    NOT NULL,    -- ISO date
    gross_pnl     REAL    NOT NULL,
    commission    REAL    NOT NULL,
    slippage      REAL    NOT NULL,
    net_pnl       REAL    NOT NULL,
    engine        TEXT,
    closed_at     TEXT    NOT NULL     -- ISO datetime (UTC)
);

CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      TEXT    UNIQUE NOT NULL,
    symbol        TEXT    NOT NULL,
    side          TEXT    NOT NULL,
    quantity      INTEGER NOT NULL,
    price         REAL,
    status        TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    filled_at     TEXT,
    fill_price    REAL
);

CREATE TABLE IF NOT EXISTS scan_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_at    TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    action        TEXT    NOT NULL,
    score         REAL,
    regime        TEXT,
    engine        TEXT
);

CREATE TABLE IF NOT EXISTS equity_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_date TEXT    UNIQUE NOT NULL,  -- ISO date
    cash          REAL    NOT NULL,
    market_value  REAL    NOT NULL,
    nav           REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS monitor_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at            TEXT    NOT NULL,
    run_type          TEXT    NOT NULL,   -- 'INTRADAY' | 'EOD'
    positions_checked INTEGER DEFAULT 0,
    stops_hit         TEXT    DEFAULT '[]',
    tps_hit           TEXT    DEFAULT '[]',
    trails_updated    TEXT    DEFAULT '[]',
    new_signals       TEXT    DEFAULT '[]',
    prices            TEXT    DEFAULT '{}'
);
"""


@dataclass
class Position:
    symbol: str
    qty: int
    avg_price: float
    stop_loss: float
    take_profit: float
    buy_date: str           # ISO date
    engine: str = ""
    entry_atr: float = 0.0  # ATR at entry — used for trailing stop distance
    trail_active: bool = False  # True once price crossed +1R

    def market_value(self, current_price: float) -> float:
        return self.qty * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        gross = self.qty * (current_price - self.avg_price)
        buy_cost = self.qty * self.avg_price * (_COMMISSION_RATE + _SLIPPAGE_RATE)
        sell_cost = self.qty * current_price * (_COMMISSION_RATE + _SLIPPAGE_RATE)
        return gross - buy_cost - sell_cost


@dataclass
class TradeRecord:
    symbol: str
    quantity: int
    entry_price: float
    exit_price: float
    entry_date: str
    exit_date: str
    gross_pnl: float
    commission: float
    slippage: float
    net_pnl: float
    engine: str = ""

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0


class PortfolioManager:
    def __init__(
        self,
        initial_cash: float = 500_000_000,
        db_path: Path | None = None,
        portfolio_path: Path | None = None,
    ) -> None:
        self._db_path = Path(db_path) if db_path is not None else _DEFAULT_DB_PATH
        self._portfolio_path = Path(portfolio_path) if portfolio_path is not None else _DEFAULT_PORTFOLIO_PATH

        self._cash: float = initial_cash
        self._positions: Dict[str, Position] = {}
        self._trades: List[TradeRecord] = []

        self._equity_week_start: float = initial_cash
        self._week_start_date: str = self._current_monday()

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.load_state()

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def open_position(self, position: Position) -> None:
        if position.symbol in self._positions:
            logger.warning("open_position: %s already open — ignored", position.symbol)
            return
        cost = position.qty * position.avg_price * (1 + _COMMISSION_RATE + _SLIPPAGE_RATE)
        self._cash -= cost
        self._positions[position.symbol] = position
        logger.info("Opened %s × %d @ %.0f", position.symbol, position.qty, position.avg_price)

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_date: str | None = None,
    ) -> Optional[TradeRecord]:
        pos = self._positions.pop(symbol, None)
        if pos is None:
            logger.warning("close_position: %s not in portfolio — ignored", symbol)
            return None

        exit_date = exit_date or date.today().isoformat()
        gross = pos.qty * (exit_price - pos.avg_price)
        commission = pos.qty * (pos.avg_price + exit_price) * _COMMISSION_RATE
        slippage   = pos.qty * (pos.avg_price + exit_price) * _SLIPPAGE_RATE
        net = gross - commission - slippage

        proceeds = pos.qty * exit_price * (1 - _COMMISSION_RATE - _SLIPPAGE_RATE)
        self._cash += proceeds

        trade = TradeRecord(
            symbol=symbol,
            quantity=pos.qty,
            entry_price=pos.avg_price,
            exit_price=exit_price,
            entry_date=pos.buy_date,
            exit_date=exit_date,
            gross_pnl=gross,
            commission=commission,
            slippage=slippage,
            net_pnl=net,
            engine=pos.engine,
        )
        self._trades.append(trade)
        self._write_trade_to_db(trade)
        logger.info("Closed %s @ %.0f  net_pnl=%.0f", symbol, exit_price, net)
        return trade

    def update_stop(self, symbol: str, new_stop: float) -> None:
        if symbol in self._positions:
            self._positions[symbol].stop_loss = new_stop

    # ------------------------------------------------------------------
    # P&L & equity
    # ------------------------------------------------------------------

    def get_unrealized_pnl(self, prices: Dict[str, float]) -> float:
        return sum(pos.unrealized_pnl(prices[sym]) for sym, pos in self._positions.items() if sym in prices)

    def get_market_value(self, prices: Dict[str, float]) -> float:
        return sum(pos.qty * prices[sym] for sym, pos in self._positions.items() if sym in prices)

    def get_equity(self, prices: Dict[str, float]) -> float:
        return self._cash + self.get_market_value(prices)

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    @property
    def trades(self) -> List[TradeRecord]:
        return list(self._trades)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def win_rate(self) -> float:
        if not self._trades:
            return 0.0
        return sum(1 for t in self._trades if t.is_win) / len(self._trades)

    def profit_factor(self) -> float:
        gross_wins  = sum(t.net_pnl for t in self._trades if t.net_pnl > 0)
        gross_losses = abs(sum(t.net_pnl for t in self._trades if t.net_pnl < 0))
        if gross_losses == 0:
            return float("inf") if gross_wins > 0 else 0.0
        return gross_wins / gross_losses

    def max_drawdown(self, equity_curve: List[float]) -> float:
        """Return MDD as a positive fraction (e.g. 0.25 = 25%)."""
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        mdd = 0.0
        for v in equity_curve:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > mdd:
                mdd = dd
        return mdd

    def sharpe_ratio(self, equity_curve: List[float], periods_per_year: int = 252) -> float:
        if len(equity_curve) < 2:
            return 0.0
        returns = pd.Series(equity_curve).pct_change().dropna()
        if returns.std() == 0:
            return 0.0
        return float((returns.mean() / returns.std()) * math.sqrt(periods_per_year))

    def sortino_ratio(self, equity_curve: List[float], periods_per_year: int = 252) -> float:
        if len(equity_curve) < 2:
            return 0.0
        returns = pd.Series(equity_curve).pct_change().dropna()
        downside = returns[returns < 0]
        downside_std = float(np.sqrt((downside ** 2).mean())) if not downside.empty else 0.0
        if downside_std == 0:
            return 0.0
        return float((returns.mean() / downside_std) * math.sqrt(periods_per_year))

    # ------------------------------------------------------------------
    # Weekly P&L tracking
    # ------------------------------------------------------------------

    def weekly_pnl_pct(self, current_equity: float) -> float:
        self._maybe_reset_weekly(current_equity)
        return (current_equity - self._equity_week_start) / self._equity_week_start

    def _maybe_reset_weekly(self, current_equity: float) -> None:
        today_monday = self._current_monday()
        if today_monday != self._week_start_date:
            self._equity_week_start = current_equity
            self._week_start_date = today_monday

    @staticmethod
    def _current_monday() -> str:
        today = date.today()
        monday = today - pd.tseries.offsets.Week(weekday=0) if today.weekday() != 0 else today
        # simpler:
        monday = today - pd.Timedelta(days=today.weekday())
        return monday.isoformat()

    # ------------------------------------------------------------------
    # Equity history
    # ------------------------------------------------------------------

    def record_equity_snapshot(self, prices: Dict[str, float]) -> None:
        today = date.today().isoformat()
        cash = self._cash
        mv = self.get_market_value(prices)
        nav = cash + mv
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO equity_history(recorded_date, cash, market_value, nav) VALUES (?,?,?,?)",
                (today, cash, mv, nav),
            )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_state(self) -> None:
        state = {
            "cash": self._cash,
            "equity_week_start": self._equity_week_start,
            "week_start_date": self._week_start_date,
            "positions": {sym: asdict(pos) for sym, pos in self._positions.items()},
        }
        self._portfolio_path.parent.mkdir(parents=True, exist_ok=True)
        self._portfolio_path.write_text(json.dumps(state, indent=2))

    def load_state(self) -> None:
        if not self._portfolio_path.exists():
            return
        try:
            state = json.loads(self._portfolio_path.read_text())
            self._cash = state.get("cash", self._cash)
            self._equity_week_start = state.get("equity_week_start", self._cash)
            self._week_start_date = state.get("week_start_date", self._current_monday())
            self._positions = {
                sym: Position(**pos)
                for sym, pos in state.get("positions", {}).items()
            }
            self._trades = self._load_trades_from_db()
        except Exception as exc:
            logger.error("load_state failed: %s", exc)

    def _load_trades_from_db(self) -> List[TradeRecord]:
        if not self._db_path.exists():
            return []
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT symbol, quantity, entry_price, exit_price, entry_date, exit_date, "
                    "gross_pnl, commission, slippage, net_pnl, engine FROM trades"
                ).fetchall()
            return [
                TradeRecord(
                    symbol=r[0], quantity=r[1], entry_price=r[2], exit_price=r[3],
                    entry_date=r[4], exit_date=r[5], gross_pnl=r[6],
                    commission=r[7], slippage=r[8], net_pnl=r[9], engine=r[10] or "",
                )
                for r in rows
            ]
        except Exception as exc:
            logger.error("_load_trades_from_db failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA_SQL)

    def _write_trade_to_db(self, trade: TradeRecord) -> None:
        from datetime import timezone
        closed_at = datetime.now(tz=timezone.utc).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO trades(symbol, side, quantity, entry_price, exit_price, "
                "entry_date, exit_date, gross_pnl, commission, slippage, net_pnl, engine, closed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    trade.symbol, "BUY", trade.quantity, trade.entry_price, trade.exit_price,
                    trade.entry_date, trade.exit_date, trade.gross_pnl,
                    trade.commission, trade.slippage, trade.net_pnl,
                    trade.engine, closed_at,
                ),
            )
