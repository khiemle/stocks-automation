from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from core.protocols import AccountBalance, BrokerProtocol, OrderResult, OrderStatus, StockPosition

logger = logging.getLogger(__name__)

_COMMISSION_RATE = 0.0015   # 0.15% per side
_SLIPPAGE_RATE   = 0.0010   # 0.10% per side


@dataclass
class _PendingOrder:
    order_id: str
    symbol: str
    side: str           # "B" | "S"
    quantity: int
    price: float | None
    order_type: str     # "LO" | "ATO"
    placed_date: str    # ISO date


@dataclass
class _FilledTrade:
    symbol: str
    side: str
    quantity: int
    fill_price: float
    fill_date: str


class SimulatedBroker:
    """
    Paper-trading broker: fills orders at T+1 open price with commission + slippage.
    T+2 rule: cannot sell within 2 business days of the buy date.
    """

    name = "SimulatedBroker"

    def __init__(self, initial_cash: float = 500_000_000) -> None:
        self._cash: float = initial_cash
        self._positions: Dict[str, _FilledTrade] = {}   # symbol → most recent BUY
        self._pending: Dict[str, _PendingOrder] = {}    # order_id → order
        self._filled: List[_FilledTrade] = []
        self._order_statuses: Dict[str, OrderStatus] = {}

    # ------------------------------------------------------------------
    # BrokerProtocol interface
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        price: float | None,
        account: str,
        sim_date: str | None = None,    # override "today" for backtesting
    ) -> OrderResult:
        # T+2 guard: reject SELL if position was bought within 2 business days
        if side == "S" and symbol in self._positions:
            buy_date = pd.Timestamp(self._positions[symbol].fill_date)
            today = pd.Timestamp(sim_date) if sim_date else pd.Timestamp(date.today())
            bd = len(pd.bdate_range(start=buy_date, end=today)) - 1
            if bd < 2:
                msg = f"T+2 violation: {symbol} bought {buy_date.date()}, only {bd} business day(s) elapsed"
                logger.warning(msg)
                oid = str(uuid.uuid4())
                self._order_statuses[oid] = OrderStatus(
                    order_id=oid, status="REJECTED", filled_qty=0, fill_price=None
                )
                return OrderResult(order_id=oid, status="REJECTED", message=msg)

        oid = str(uuid.uuid4())
        order = _PendingOrder(
            order_id=oid,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            placed_date=date.today().isoformat(),
        )
        self._pending[oid] = order
        self._order_statuses[oid] = OrderStatus(
            order_id=oid, status="PENDING", filled_qty=0, fill_price=None
        )
        logger.info("Order placed: %s %s %d %s", side, symbol, quantity, oid[:8])
        return OrderResult(order_id=oid, status="PLACED", message="OK")

    def cancel_order(self, order_id: str, account: str) -> bool:
        if order_id in self._pending:
            del self._pending[order_id]
            self._order_statuses[order_id] = OrderStatus(
                order_id=order_id, status="CANCELLED", filled_qty=0, fill_price=None
            )
            return True
        return False

    def get_order_status(self, order_id: str) -> OrderStatus:
        return self._order_statuses.get(
            order_id,
            OrderStatus(order_id=order_id, status="UNKNOWN", filled_qty=0, fill_price=None),
        )

    def get_account_balance(self, account: str) -> AccountBalance:
        mv = sum(
            t.fill_price * t.quantity for t in self._positions.values()
        )
        return AccountBalance(cash=self._cash, buying_power=self._cash, nav=self._cash + mv)

    def get_stock_positions(self, account: str) -> List[StockPosition]:
        return [
            StockPosition(
                symbol=sym,
                qty=t.quantity,
                avg_price=t.fill_price,
                market_value=t.fill_price * t.quantity,
            )
            for sym, t in self._positions.items()
        ]

    # ------------------------------------------------------------------
    # Backtesting interface: fill pending orders against next-bar OHLCV
    # ------------------------------------------------------------------

    def process_next_bar(self, symbol: str, bar: pd.Series, bar_date: str) -> None:
        """
        Called by Backtester with T+1 bar.  Fills all pending orders for `symbol`
        at bar['open'] with slippage applied.
        """
        filled_ids = []
        for oid, order in list(self._pending.items()):
            if order.symbol != symbol:
                continue

            raw_open = float(bar["open"])
            if order.side == "B":
                fill_price = raw_open * (1 + _SLIPPAGE_RATE)
                cost = order.quantity * fill_price * (1 + _COMMISSION_RATE)
                if cost > self._cash:
                    logger.warning("Insufficient cash for %s: need %.0f, have %.0f", symbol, cost, self._cash)
                    self._order_statuses[oid] = OrderStatus(
                        order_id=oid, status="REJECTED", filled_qty=0, fill_price=None
                    )
                    filled_ids.append(oid)
                    continue
                self._cash -= cost
                trade = _FilledTrade(symbol=symbol, side="B", quantity=order.quantity,
                                     fill_price=fill_price, fill_date=bar_date)
                self._positions[symbol] = trade
                self._filled.append(trade)

            else:  # "S"
                fill_price = raw_open * (1 - _SLIPPAGE_RATE)
                proceeds = order.quantity * fill_price * (1 - _COMMISSION_RATE)
                self._cash += proceeds
                trade = _FilledTrade(symbol=symbol, side="S", quantity=order.quantity,
                                     fill_price=fill_price, fill_date=bar_date)
                self._filled.append(trade)
                self._positions.pop(symbol, None)

            self._order_statuses[oid] = OrderStatus(
                order_id=oid, status="FILLED",
                filled_qty=order.quantity, fill_price=fill_price,
            )
            filled_ids.append(oid)
            logger.debug("Filled %s %s %d @ %.0f on %s", order.side, symbol, order.quantity, fill_price, bar_date)

        for oid in filled_ids:
            self._pending.pop(oid, None)
