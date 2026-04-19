from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class PositionSizeResult:
    shares: int
    stop_price: float
    take_profit: float
    stop_distance: float
    risk_amount: float
    warnings: list[str] = field(default_factory=list)
    eligible: bool = True


class RiskEngine:
    HOSE_BAND = 0.07
    HNX_BAND = 0.10
    ATR_STOP_MULT = 1.5
    ATR_TP_MULT = 4.5        # deprecated — kept for backwards compat; trailing stop superseded fixed TP
    ATR_TRAIL_MULT = 2.0     # trailing stop distance once +1R reached
    ATR_TRAIL_TRIGGER = 1.5  # activate trailing when gain >= 1.5 × ATR (= 1R)
    RISK_PCT = 0.02          # 2% risk per trade
    MAX_POSITION_PCT = 0.20  # max 20% capital per position (half-Kelly)
    MAX_ADV_PCT = 0.05       # max 5% of average daily volume
    WEEKLY_WARN_PCT = 0.015  # -1.5% weekly → warn
    WEEKLY_STOP_PCT = 0.030  # -3.0% weekly → stop new positions
    CIRCUIT_MULT = 1.50      # 150% of backtest MDD triggers circuit breaker

    def __init__(self, backtest_mdd: float, capital: float) -> None:
        """
        backtest_mdd: positive decimal (e.g. 0.12 for 12% max drawdown)
        capital: starting portfolio equity in VND
        """
        self.backtest_mdd = backtest_mdd
        self.capital = capital
        self._week_start_equity: float = capital
        self._circuit_broken: bool = False
        self._stop_new_positions: bool = False

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def compute_position_size(
        self,
        close: float,
        atr: float,
        exchange: str = "HOSE",
        adv: float | None = None,
    ) -> PositionSizeResult:
        warnings: list[str] = []

        stop_distance = atr * self.ATR_STOP_MULT
        stop_price = close - stop_distance
        take_profit = close + atr * self.ATR_TP_MULT

        # Price band check — stop must be reachable within a single session
        band = self.HOSE_BAND if exchange.upper() == "HOSE" else self.HNX_BAND
        floor_price = close * (1 - band)
        if stop_price < floor_price:
            warnings.append(
                f"Stop {stop_price:.0f} < price band floor {floor_price:.0f} "
                f"({exchange} ±{band * 100:.0f}%) — entry skipped"
            )
            return PositionSizeResult(
                shares=0,
                stop_price=stop_price,
                take_profit=take_profit,
                stop_distance=stop_distance,
                risk_amount=0.0,
                warnings=warnings,
                eligible=False,
            )

        # 2% risk sizing
        if stop_distance <= 0:
            return PositionSizeResult(
                shares=0, stop_price=stop_price, take_profit=take_profit,
                stop_distance=stop_distance, risk_amount=0.0,
                warnings=["stop_distance <= 0"], eligible=False,
            )
        max_loss = self.capital * self.RISK_PCT
        shares = int(max_loss / stop_distance)

        # Half-Kelly: cap at 20% of portfolio
        if close > 0:
            max_by_capital = int(self.capital * self.MAX_POSITION_PCT / close)
            shares = min(shares, max_by_capital)

        # Max 5% ADV
        if adv is not None and adv > 0:
            max_by_adv = int(adv * self.MAX_ADV_PCT)
            if shares > max_by_adv:
                warnings.append(
                    f"Size capped {shares} → {max_by_adv} (5% ADV limit)"
                )
                shares = max_by_adv

        # Round down to VN lot size (100 shares)
        shares = (shares // 100) * 100

        risk_amount = shares * stop_distance

        return PositionSizeResult(
            shares=shares,
            stop_price=stop_price,
            take_profit=take_profit,
            stop_distance=stop_distance,
            risk_amount=risk_amount,
            warnings=warnings,
            eligible=shares > 0,
        )

    # ------------------------------------------------------------------
    # Trailing stop
    # ------------------------------------------------------------------

    def trailing_stop_update(
        self,
        current_stop: float,
        current_price: float,
        atr: float,
    ) -> float:
        """Return updated trailing stop — never decreases."""
        new_stop = current_price - atr * self.ATR_STOP_MULT
        return max(current_stop, new_stop)

    # ------------------------------------------------------------------
    # Circuit breaker
    # ------------------------------------------------------------------

    def check_circuit_breaker(self, current_mdd: float) -> bool:
        """Return True (and latch) when real MDD >= 150% of backtest MDD."""
        if current_mdd >= self.backtest_mdd * self.CIRCUIT_MULT:
            self.stop_all()
        return self._circuit_broken

    def stop_all(self) -> None:
        self._circuit_broken = True
        self._stop_new_positions = True

    # ------------------------------------------------------------------
    # Weekly loss limits
    # ------------------------------------------------------------------

    def reset_week(self, current_equity: float) -> None:
        """Call at the start of each trading week (Monday 08:00)."""
        self._week_start_equity = current_equity
        self._stop_new_positions = False

    def check_weekly_loss(self, current_equity: float) -> str:
        """Return 'OK', 'WARN', or 'STOP'.  Sets flag when STOP."""
        if self._week_start_equity <= 0:
            return "OK"
        pct = (current_equity - self._week_start_equity) / self._week_start_equity
        if pct <= -self.WEEKLY_STOP_PCT:
            self._stop_new_positions = True
            return "STOP"
        if pct <= -self.WEEKLY_WARN_PCT:
            return "WARN"
        return "OK"

    def is_new_position_allowed(self) -> bool:
        return not self._circuit_broken and not self._stop_new_positions

    # ------------------------------------------------------------------
    # T+2 enforcement
    # ------------------------------------------------------------------

    @staticmethod
    def check_t2(buy_date: date, sell_date: date) -> bool:
        """Return True if sell is permitted (>= 2 business days after buy)."""
        bdays = 0
        d = buy_date + timedelta(days=1)
        while d <= sell_date:
            if d.weekday() < 5:
                bdays += 1
            d += timedelta(days=1)
        return bdays >= 2
