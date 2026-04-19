from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from brokers.simulated_broker import _COMMISSION_RATE, _SLIPPAGE_RATE

logger = logging.getLogger(__name__)

_MARKET_DIR = Path("data/market")
_PERIODS_PER_YEAR = 252
_WARMUP_BARS = 252   # bars reserved for indicator warm-up (EMA200 needs 200+)


@dataclass
class TradeLog:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    net_pnl: float
    side: str = "BUY"


@dataclass
class BacktestMetrics:
    total_return: float      # decimal, e.g. 0.35 = 35%
    sharpe_ratio: float
    sortino_ratio: float
    information_ratio: float
    max_drawdown: float      # positive decimal
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_win: float = 0.0     # average net P&L of winning trades
    avg_loss: float = 0.0    # average net P&L of losing trades (negative)
    trades_per_year: float = 0.0
    benchmark_return: Optional[float] = None  # buy-hold of same symbol over same window
    alpha: Optional[float] = None             # total_return - benchmark_return

    def summary(self) -> str:
        ev = self.win_rate * self.avg_win + (1 - self.win_rate) * self.avg_loss
        lines = [
            f"Total Return    : {self.total_return:+.2%}",
            f"Sharpe Ratio    : {self.sharpe_ratio:.3f}",
            f"Sortino Ratio   : {self.sortino_ratio:.3f}",
            f"Information Ratio: {self.information_ratio:.3f}",
            f"Max Drawdown    : {self.max_drawdown:.2%}",
            f"Win Rate        : {self.win_rate:.2%}",
            f"Profit Factor   : {self.profit_factor:.3f}",
            f"Total Trades    : {self.total_trades}  ({self.trades_per_year:.1f}/year)",
            f"Avg Win         : {self.avg_win:+,.0f} VND",
            f"Avg Loss        : {self.avg_loss:+,.0f} VND",
            f"Expected Value  : {ev:+,.0f} VND/trade",
        ]
        if self.benchmark_return is not None:
            lines.append(f"Buy & Hold      : {self.benchmark_return:+.2%}")
            lines.append(f"Alpha (vs B&H)  : {self.alpha:+.2%}")
        return "\n".join(lines)


@dataclass
class BacktestResult:
    in_sample: BacktestMetrics
    out_of_sample: Optional[BacktestMetrics]
    trades: List[TradeLog] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["=== In-Sample ===", self.in_sample.summary()]
        if self.out_of_sample:
            lines += ["", "=== Out-of-Sample ===", self.out_of_sample.summary()]
        return "\n".join(lines)


def _buy_hold_return(df: pd.DataFrame) -> float:
    """Buy at close of warmup bar, hold to end of df, with 1 round-trip of commission+slippage."""
    if len(df) <= _WARMUP_BARS:
        return 0.0
    entry = float(df["close"].iloc[_WARMUP_BARS])
    exit_ = float(df["close"].iloc[-1])
    if entry <= 0:
        return 0.0
    gross = (exit_ - entry) / entry
    costs = 2 * (_COMMISSION_RATE + _SLIPPAGE_RATE)  # buy + sell
    return gross - costs


def _compute_metrics(
    equity_curve: List[float],
    trades: List[TradeLog],
    years: float = 1.0,
) -> BacktestMetrics:
    if not equity_curve or len(equity_curve) < 2:
        return BacktestMetrics(0, 0, 0, 0, 0, 0, 0, 0)

    returns = pd.Series(equity_curve).pct_change().dropna()
    total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]

    # Sharpe
    sharpe = float((returns.mean() / returns.std()) * math.sqrt(_PERIODS_PER_YEAR)) if returns.std() > 0 else 0.0

    # Sortino
    down = returns[returns < 0]
    down_std = float(np.sqrt((down ** 2).mean())) if not down.empty else 0.0
    sortino = float((returns.mean() / down_std) * math.sqrt(_PERIODS_PER_YEAR)) if down_std > 0 else 0.0

    # Information Ratio (strategy returns vs zero benchmark)
    ir = float(returns.mean() / returns.std() * math.sqrt(_PERIODS_PER_YEAR)) if returns.std() > 0 else 0.0

    # MDD
    peak, mdd = equity_curve[0], 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > mdd:
            mdd = dd

    # Win rate + profit factor
    wins   = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    gross_wins   = sum(t.net_pnl for t in wins)
    gross_losses = abs(sum(t.net_pnl for t in losses))
    pf = gross_wins / gross_losses if gross_losses > 0 else (float("inf") if gross_wins > 0 else 0.0)

    avg_win  = (gross_wins  / len(wins))   if wins   else 0.0
    avg_loss = (-gross_losses / len(losses)) if losses else 0.0  # negative
    n_years  = max(len(equity_curve) / _PERIODS_PER_YEAR, years)
    trades_per_year = len(trades) / n_years if n_years > 0 else 0.0

    return BacktestMetrics(
        total_return=total_return,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        information_ratio=ir,
        max_drawdown=mdd,
        win_rate=win_rate,
        profit_factor=pf,
        total_trades=len(trades),
        avg_win=avg_win,
        avg_loss=avg_loss,
        trades_per_year=trades_per_year,
    )


class Backtester:
    """
    Event-driven backtester.

    Flow per bar T:
      1. Evaluate signal on df[:T] (no look-ahead)
      2. Place order at close of T
      3. Fill at open of T+1 (via SimulatedBroker.process_next_bar)
      4. Check stop/TP vs T+1 high/low — exit same bar if triggered
    """

    def __init__(self, config: dict) -> None:
        self._config = config
        self._initial_cash: float = config["capital"]["initial"]
        self._max_positions: int = config["capital"].get("max_positions", 5)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, symbols: List[str], years: int = 3) -> BacktestResult:
        all_trades: List[TradeLog] = []
        equity_curve: List[float] = []
        benchmarks: List[float] = []

        for sym in symbols:
            df = self._load(sym, years)
            if df is None or len(df) < _WARMUP_BARS + 60:
                logger.warning("Skipping %s — insufficient data", sym)
                continue
            trades, eq = self._simulate(sym, df)
            all_trades.extend(trades)
            benchmarks.append(_buy_hold_return(df))
            if not equity_curve:
                equity_curve = eq
            else:
                # merge equity curves by adding daily P&L
                for i, v in enumerate(eq):
                    if i < len(equity_curve):
                        equity_curve[i] += v - (eq[0] if i == 0 else eq[i - 1])

        if not equity_curve:
            equity_curve = [self._initial_cash]

        metrics = _compute_metrics(equity_curve, all_trades)
        if benchmarks:
            metrics.benchmark_return = float(np.mean(benchmarks))
            metrics.alpha = metrics.total_return - metrics.benchmark_return
        return BacktestResult(in_sample=metrics, out_of_sample=None, trades=all_trades)

    def run_all(self, walk_forward: bool = False, split: float = 0.7) -> BacktestResult:
        from core.data_manager import DataManager
        from data_sources.yfinance_client import YFinanceClient

        dm = DataManager(YFinanceClient())
        symbols = list(dict.fromkeys(dm.get_universe("HOSE") + dm.get_universe("HNX")))

        if not walk_forward:
            return self.run(symbols, years=3)

        all_is_trades: List[TradeLog] = []
        all_oos_trades: List[TradeLog] = []
        all_is_eq: List[float] = []
        all_oos_eq: List[float] = []
        is_benchmarks: List[float] = []
        oos_benchmarks: List[float] = []

        for sym in symbols:
            df = self._load(sym, years=5)
            if df is None or len(df) < _WARMUP_BARS + 60:
                continue

            split_idx = int(len(df) * split)
            df_is  = df.iloc[:split_idx]
            # OOS gets its own warmup window prepended so EMA200 is calibrated
            oos_start = max(0, split_idx - _WARMUP_BARS)
            df_oos = df.iloc[oos_start:]

            is_trades, is_eq  = self._simulate(sym, df_is)
            oos_trades, oos_eq = self._simulate(sym, df_oos)

            all_is_trades.extend(is_trades)
            all_oos_trades.extend(oos_trades)
            is_benchmarks.append(_buy_hold_return(df_is))
            oos_benchmarks.append(_buy_hold_return(df_oos))
            if not all_is_eq:
                all_is_eq = is_eq
            if not all_oos_eq:
                all_oos_eq = oos_eq

        is_metrics  = _compute_metrics(all_is_eq  or [self._initial_cash], all_is_trades)
        oos_metrics = _compute_metrics(all_oos_eq or [self._initial_cash], all_oos_trades)

        if is_benchmarks:
            is_metrics.benchmark_return = float(np.mean(is_benchmarks))
            is_metrics.alpha = is_metrics.total_return - is_metrics.benchmark_return
        if oos_benchmarks:
            oos_metrics.benchmark_return = float(np.mean(oos_benchmarks))
            oos_metrics.alpha = oos_metrics.total_return - oos_metrics.benchmark_return

        return BacktestResult(
            in_sample=is_metrics,
            out_of_sample=oos_metrics,
            trades=all_is_trades + all_oos_trades,
        )

    # ------------------------------------------------------------------
    # Core simulation loop
    # ------------------------------------------------------------------

    def _simulate(self, symbol: str, df: pd.DataFrame) -> tuple[List[TradeLog], List[float]]:
        from brokers.simulated_broker import SimulatedBroker
        from signals.momentum_v1 import MomentumV1
        from core.market_regime import MarketRegime
        from core.risk_engine import RiskEngine
        from ta.volatility import AverageTrueRange

        engine = MomentumV1()
        broker = SimulatedBroker(initial_cash=self._initial_cash)
        risk = RiskEngine(backtest_mdd=0.20, capital=self._initial_cash)

        # Macro regime — shared VN30 basket; cache per Backtester instance so we
        # don't rebuild it for every symbol.
        if not hasattr(self, "_market_regime"):
            try:
                self._market_regime = MarketRegime()
            except Exception as exc:
                logger.warning("MarketRegime unavailable (%s); macro filter off", exc)
                self._market_regime = None
        regime_obj = self._market_regime

        # Pre-compute ATR for entire series once
        atr_series = AverageTrueRange(df["high"], df["low"], df["close"], window=14) \
                         .average_true_range()

        trades: List[TradeLog] = []
        equity: List[float] = [self._initial_cash]

        open_position: Optional[dict] = None   # {entry_price, qty, stop, tp, entry_date, entry_bar}
        pending_signal: Optional[str] = None   # "BUY" | "SELL"
        self._pending_regime: str = "TRENDING"  # regime at signal time, used when filling BUY

        for i in range(1, len(df)):
            # Skip warmup period — indicators (esp. EMA200) need prior history
            in_warmup = i < _WARMUP_BARS
            bar      = df.iloc[i]
            bar_date = str(df.index[i].date())

            # ── Fill pending BUY at T+1 open ─────────────────────────
            if pending_signal == "BUY" and open_position is None:
                qty = self._size(broker, bar, risk, symbol)
                if qty > 0:
                    broker.place_order(symbol, "B", qty, "ATO", None, "paper",
                                       sim_date=bar_date)
                    broker.process_next_bar(symbol, bar, bar_date)
                    filled = [t for t in broker._filled if t.side == "B" and t.fill_date == bar_date]
                    if filled:
                        fp      = filled[-1].fill_price
                        qty_f   = filled[-1].quantity
                        atr_val = float(atr_series.iloc[i]) if not np.isnan(atr_series.iloc[i]) else fp * 0.02
                        stop    = fp - risk.ATR_STOP_MULT * atr_val
                        # Adaptive TP: SIDEWAYS → 2×ATR, VOLATILE → 1.5×ATR, TRENDING → None (trail)
                        _regime = getattr(self, "_pending_regime", "TRENDING")
                        if _regime == "SIDEWAYS":
                            _tp = fp + 2.0 * atr_val
                        elif _regime == "VOLATILE":
                            _tp = fp + 1.5 * atr_val
                        else:
                            _tp = None
                        open_position = dict(entry_price=fp, qty=qty_f, stop=stop,
                                             take_profit=_tp, entry_regime=_regime,
                                             entry_atr=atr_val, trail_active=False,
                                             entry_date=bar_date, entry_bar=i)
                self._pending_regime = "TRENDING"
                pending_signal = None

            # ── Fill pending SELL at T+1 open (T+2 enforced) ────────
            elif pending_signal == "SELL" and open_position is not None:
                result = broker.place_order(symbol, "S", open_position["qty"],
                                            "ATO", None, "paper", sim_date=bar_date)
                if result.status == "REJECTED":
                    # T+2 not satisfied yet — cancel signal, keep holding
                    pending_signal = None
                else:
                    broker.process_next_bar(symbol, bar, bar_date)
                    filled = [t for t in broker._filled if t.side == "S" and t.fill_date == bar_date]
                    if filled:
                        xp = filled[-1].fill_price
                        trades.append(self._make_trade(symbol, open_position, xp, bar_date))
                        open_position = None
                    pending_signal = None

            # ── Intraday stop/TP check (never on entry bar; respect T+2) ──
            if open_position is not None and i > open_position["entry_bar"]:
                buy_ts  = pd.Timestamp(open_position["entry_date"])
                sell_ts = pd.Timestamp(bar_date)
                bd_elapsed = len(pd.bdate_range(start=buy_ts, end=sell_ts)) - 1
                t2_clear = bd_elapsed >= 2

                if t2_clear:
                    lo, hi = float(bar["low"]), float(bar["high"])
                    if lo <= open_position["stop"]:
                        exit_price = open_position["stop"]
                        trades.append(self._make_trade(symbol, open_position, exit_price, bar_date))
                        broker._cash += open_position["qty"] * exit_price * (1 - _COMMISSION_RATE - _SLIPPAGE_RATE)
                        broker._positions.pop(symbol, None)
                        open_position = None
                    else:
                        # Adaptive TP check for SIDEWAYS/VOLATILE regimes
                        tp = open_position.get("take_profit")
                        if tp is not None and hi >= tp:
                            trades.append(self._make_trade(symbol, open_position, tp, bar_date))
                            broker._cash += open_position["qty"] * tp * (1 - _COMMISSION_RATE - _SLIPPAGE_RATE)
                            broker._positions.pop(symbol, None)
                            open_position = None
                        else:
                            # Trailing stop: activate when high crosses +1R, then ratchet
                            ep = open_position["entry_price"]
                            atr_e = open_position["entry_atr"]
                            trigger = ep + risk.ATR_TRAIL_TRIGGER * atr_e
                            if not open_position["trail_active"] and hi >= trigger:
                                open_position["trail_active"] = True
                                # Breakeven stop: kéo stop lên entry khi +1R đạt được
                                open_position["stop"] = max(open_position["stop"], ep)
                            if open_position["trail_active"]:
                                new_stop = hi - risk.ATR_TRAIL_MULT * atr_e
                                if new_stop > open_position["stop"]:
                                    open_position["stop"] = new_stop

            # ── Generate signal on close of bar i ───────────────────
            # Only signal if position was open/closed BEFORE this bar
            # (avoids immediate re-entry on the stop-out bar)
            if pending_signal is None and not in_warmup:
                window = df.iloc[: i + 1]
                macro_ctx = regime_obj.context(df.index[i]) if regime_obj else None
                try:
                    result = engine.evaluate(window, foreign_flow=None,
                                             market_context=macro_ctx)
                except Exception:
                    equity.append(equity[-1])
                    continue

                if result.action == "BUY" and open_position is None:
                    pending_signal = "BUY"
                    self._pending_regime = result.regime
                elif result.action == "SELL" and open_position is not None:
                    pending_signal = "SELL"

            # ── Mark-to-market equity ────────────────────────────────
            mv = (open_position["qty"] * float(bar["close"])) if open_position else 0.0
            equity.append(broker._cash + mv)

        # Close any open position at last bar close
        if open_position is not None:
            last_bar = df.iloc[-1]
            xp = float(last_bar["close"]) * (1 - _SLIPPAGE_RATE)
            trades.append(self._make_trade(symbol, open_position, xp, str(df.index[-1].date())))

        return trades, equity

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_trade(symbol: str, pos: dict, exit_price: float, exit_date: str) -> TradeLog:
        gross = pos["qty"] * (exit_price - pos["entry_price"])
        commission = pos["qty"] * (pos["entry_price"] + exit_price) * _COMMISSION_RATE
        slippage   = pos["qty"] * (pos["entry_price"] + exit_price) * _SLIPPAGE_RATE
        return TradeLog(
            symbol=symbol,
            entry_date=pos["entry_date"],
            exit_date=exit_date,
            entry_price=pos["entry_price"],
            exit_price=exit_price,
            quantity=pos["qty"],
            net_pnl=gross - commission - slippage,
        )

    def _size(self, broker, bar: pd.Series, risk: RiskEngine, symbol: str) -> int:
        from ta.volatility import AverageTrueRange
        close = float(bar["close"])
        # minimal sizing: 2% risk of current cash
        cash = broker._cash
        atr = close * 0.02  # fallback; real ATR computed post-fill
        stop_dist = risk.ATR_STOP_MULT * atr
        if stop_dist <= 0:
            return 0
        raw_shares = int((cash * risk.RISK_PCT) / stop_dist)
        max_shares = int((cash * risk.MAX_POSITION_PCT) / close)
        qty = min(raw_shares, max_shares)
        return max(qty, 0)

    @staticmethod
    def _load(symbol: str, years: int) -> Optional[pd.DataFrame]:
        # Load warmup bars + trading window so EMA200 is calibrated on pre-window data
        days = years * 365 + _WARMUP_BARS
        for exchange in ("HOSE", "HNX"):
            path = _MARKET_DIR / exchange / f"{symbol}.parquet"
            if path.exists():
                df = pd.read_parquet(path)
                return df.tail(days)
        return None
