"""
Portfolio backtest on VN30 — single cash pool, max_positions constraint.

Phản ánh swing trading thực tế: nhiều symbol cùng emit signal trong một phiên,
hệ thống rank theo score và chọn top-K để fill slot còn trống. Đây là cách đánh
giá đúng cho MomentumV1 (short-term swing), khác hẳn với chạy độc lập từng symbol.

Outputs:
    data/backtest_portfolio_vn30_trades.csv    — per-trade log
    data/backtest_portfolio_vn30_equity.csv    — daily equity curve
    data/backtest_portfolio_vn30_periodic.csv  — return by year + quarter
    stdout: aggregate + periodic tables
"""
from __future__ import annotations

import csv
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from brokers.simulated_broker import _COMMISSION_RATE, _SLIPPAGE_RATE  # noqa: E402
from core.market_regime import MarketRegime  # noqa: E402
from core.risk_engine import RiskEngine  # noqa: E402
from core.sector_map import can_add_to_sector  # noqa: E402
from signals.momentum_v1 import MomentumV1  # noqa: E402
from ta.volatility import AverageTrueRange  # noqa: E402

_MAX_SECTOR_POSITIONS = 2  # max open positions per sector at any time

_WARMUP = 252
_PERIODS_PER_YEAR = 252


# ─────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────
@dataclass
class Position:
    symbol: str
    qty: int
    entry_price: float
    stop: float
    entry_atr: float         # ATR at entry — frozen for +1R trigger
    entry_date: pd.Timestamp
    entry_idx: int           # global date index
    trail_active: bool = False  # becomes True once high reaches entry + 1R
    take_profit: float | None = None  # fixed TP for SIDEWAYS/VOLATILE regimes; None = trail only
    entry_regime: str = "TRENDING"


@dataclass
class TradeLog:
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    quantity: int
    net_pnl: float
    exit_reason: str  # "TP" | "STOP" | "SELL" | "EOD"
    holding_days: int


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _load_vn30() -> list[str]:
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


def _load_market(symbol: str, years: int) -> Optional[pd.DataFrame]:
    for exch in ("HOSE", "HNX"):
        p = Path("data/market") / exch / f"{symbol}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            return df.tail(years * 365 + _WARMUP)
    return None


def _compute_trade_pnl(entry_price: float, exit_price: float, qty: int) -> float:
    gross = qty * (exit_price - entry_price)
    comm = qty * (entry_price + exit_price) * _COMMISSION_RATE
    slip = qty * (entry_price + exit_price) * _SLIPPAGE_RATE
    return gross - comm - slip


# ─────────────────────────────────────────────────────────────────────
# Portfolio backtester
# ─────────────────────────────────────────────────────────────────────
def run_portfolio(
    symbols: list[str],
    initial_cash: float = 500_000_000,
    max_positions: int = 5,
    years: int = 5,
) -> dict:
    # 1. Load data
    market: dict[str, pd.DataFrame] = {}
    for s in symbols:
        df = _load_market(s, years)
        if df is None or len(df) < _WARMUP + 60:
            continue
        market[s] = df
    if not market:
        raise RuntimeError("No market data loaded")

    # 2. Union of all dates
    all_dates_set: set[pd.Timestamp] = set()
    for df in market.values():
        all_dates_set.update(df.index)
    all_dates = pd.DatetimeIndex(sorted(all_dates_set))

    # 3. Precompute ATR series (used for sizing + stop/TP)
    atr_cache: dict[str, pd.Series] = {}
    for s, df in market.items():
        atr_cache[s] = AverageTrueRange(
            df["high"], df["low"], df["close"], window=14
        ).average_true_range()

    # 4. State
    cash = initial_cash
    positions: dict[str, Position] = {}
    trades: list[TradeLog] = []
    equity_curve: list[tuple[pd.Timestamp, float]] = []
    # pending queues (set yesterday, executed at today's open)
    pending_buys: list[tuple[str, float, str]] = []  # [(symbol, score, regime)]
    pending_sells: set[str] = set()

    engine = MomentumV1()
    risk = RiskEngine(backtest_mdd=0.20, capital=initial_cash)
    # Macro regime filter — same VN30 universe as symbols we trade
    regime = MarketRegime(symbols=list(market.keys()))

    # First tradable date = _WARMUP bars after the earliest date with enough history
    # per symbol. Simpler: iterate from all_dates[_WARMUP:] (good enough — symbols
    # whose series is shorter will be silently skipped by `date not in df.index`).
    start_pos = _WARMUP
    n_dates = len(all_dates)

    for idx in range(start_pos, n_dates):
        date = all_dates[idx]

        # ─────────────────────────────────────────────────────
        # A) Fill pending SELLs at today's open (T+2 check)
        # ─────────────────────────────────────────────────────
        to_remove_from_pending: list[str] = []
        for sym in list(pending_sells):
            if sym not in positions:
                to_remove_from_pending.append(sym)
                continue
            pos = positions[sym]
            bd = len(pd.bdate_range(pos.entry_date, date)) - 1
            if bd < 2:
                # keep pending, try again tomorrow
                continue
            df = market.get(sym)
            if df is None or date not in df.index:
                continue
            open_p = float(df.loc[date, "open"])
            proceeds = pos.qty * open_p * (1 - _COMMISSION_RATE - _SLIPPAGE_RATE)
            cash += proceeds
            trades.append(TradeLog(
                symbol=sym,
                entry_date=pos.entry_date,
                exit_date=date,
                entry_price=pos.entry_price,
                exit_price=open_p,
                quantity=pos.qty,
                net_pnl=_compute_trade_pnl(pos.entry_price, open_p, pos.qty),
                exit_reason="SELL",
                holding_days=(date - pos.entry_date).days,
            ))
            del positions[sym]
            to_remove_from_pending.append(sym)
        for s in to_remove_from_pending:
            pending_sells.discard(s)

        # ─────────────────────────────────────────────────────
        # B) Fill pending BUYs at today's open (rank by score, fill slots)
        # ─────────────────────────────────────────────────────
        slots = max_positions - len(positions)
        if slots > 0 and pending_buys:
            pending_buys.sort(key=lambda x: -x[1])
            for sym, score, entry_regime in pending_buys:
                if slots <= 0:
                    break
                if sym in positions:
                    continue
                df = market.get(sym)
                if df is None or date not in df.index:
                    continue
                bar = df.loc[date]
                open_p = float(bar["open"])
                atr_v = atr_cache[sym].get(date)
                if atr_v is None or pd.isna(atr_v):
                    atr_v = open_p * 0.02
                stop_dist = risk.ATR_STOP_MULT * atr_v
                if stop_dist <= 0:
                    continue

                # Size against current cash (not frozen initial)
                risk_budget = cash * risk.RISK_PCT
                max_by_cap = cash * risk.MAX_POSITION_PCT / open_p
                raw_shares = min(risk_budget / stop_dist, max_by_cap)
                qty = int(raw_shares // 100 * 100)
                if qty < 100:
                    continue
                cost = qty * open_p * (1 + _COMMISSION_RATE + _SLIPPAGE_RATE)
                if cost > cash:
                    # shrink to available cash
                    max_qty = int(
                        (cash / (open_p * (1 + _COMMISSION_RATE + _SLIPPAGE_RATE)))
                        // 100 * 100
                    )
                    if max_qty < 100:
                        continue
                    qty = max_qty
                    cost = qty * open_p * (1 + _COMMISSION_RATE + _SLIPPAGE_RATE)

                # Sector concentration check: max 2 positions per sector
                if not can_add_to_sector(sym, list(positions.keys()), _MAX_SECTOR_POSITIONS):
                    continue

                # Adaptive TP by regime: SIDEWAYS → 2×ATR, VOLATILE → 1.5×ATR, TRENDING → trail only
                if entry_regime == "SIDEWAYS":
                    tp = open_p + 2.0 * atr_v
                elif entry_regime == "VOLATILE":
                    tp = open_p + 1.5 * atr_v
                else:
                    tp = None

                cash -= cost
                positions[sym] = Position(
                    symbol=sym,
                    qty=qty,
                    entry_price=open_p,
                    stop=open_p - risk.ATR_STOP_MULT * atr_v,
                    entry_atr=atr_v,
                    entry_date=date,
                    entry_idx=idx,
                    take_profit=tp,
                    entry_regime=entry_regime,
                )
                slots -= 1
        pending_buys = []

        # ─────────────────────────────────────────────────────
        # C) Intraday stop check + trailing stop update (T+2 only)
        # ─────────────────────────────────────────────────────
        to_close: list[tuple[str, float, str]] = []
        for sym, pos in positions.items():
            if idx <= pos.entry_idx:
                continue
            bd = len(pd.bdate_range(pos.entry_date, date)) - 1
            if bd < 2:
                continue
            df = market.get(sym)
            if df is None or date not in df.index:
                continue
            bar = df.loc[date]
            lo = float(bar["low"])
            hi = float(bar["high"])
            # Stop check fires first (conservative when stop and TP both hit on same bar)
            if lo <= pos.stop:
                reason = "TRAIL" if pos.trail_active else "STOP"
                to_close.append((sym, pos.stop, reason))
                continue
            # Adaptive TP check: SIDEWAYS/VOLATILE have a fixed take-profit target
            if pos.take_profit is not None and hi >= pos.take_profit:
                to_close.append((sym, pos.take_profit, "TP"))
                continue
            # Trail activation: high crossed entry + 1R (TRENDING regime uses trailing only)
            trigger = pos.entry_price + risk.ATR_TRAIL_TRIGGER * pos.entry_atr
            if not pos.trail_active and hi >= trigger:
                pos.trail_active = True
                # Breakeven stop: kéo stop lên entry khi +1R đạt được → loại bỏ loss từ winner
                pos.stop = max(pos.stop, pos.entry_price)
            if pos.trail_active:
                new_stop = hi - risk.ATR_TRAIL_MULT * pos.entry_atr
                if new_stop > pos.stop:
                    pos.stop = new_stop
        for sym, exit_p, reason in to_close:
            pos = positions[sym]
            proceeds = pos.qty * exit_p * (1 - _COMMISSION_RATE - _SLIPPAGE_RATE)
            cash += proceeds
            trades.append(TradeLog(
                symbol=sym,
                entry_date=pos.entry_date,
                exit_date=date,
                entry_price=pos.entry_price,
                exit_price=exit_p,
                quantity=pos.qty,
                net_pnl=_compute_trade_pnl(pos.entry_price, exit_p, pos.qty),
                exit_reason=reason,
                holding_days=(date - pos.entry_date).days,
            ))
            del positions[sym]

        # ─────────────────────────────────────────────────────
        # D) Generate signals at close → queue for tomorrow's open
        # ─────────────────────────────────────────────────────
        macro_ctx = regime.context(date)
        portfolio_full = len(positions) >= max_positions
        for sym, df in market.items():
            if date not in df.index:
                continue
            window_end = df.index.get_loc(date)
            if window_end < _WARMUP:
                continue
            window = df.iloc[: window_end + 1]
            if sym in positions:
                # can we SELL it?
                try:
                    res = engine.evaluate(window, foreign_flow=None,
                                          market_context=macro_ctx)
                except Exception:
                    continue
                if res.action == "SELL":
                    pending_sells.add(sym)
                continue

            if portfolio_full and len(pending_buys) >= max_positions:
                # skip evaluation — no slot even after ranking
                continue

            # eligibility check (skip symbols locked, low liquidity etc.)
            eligible, _ = engine.is_eligible(
                window, sym,
                portfolio_symbols=list(positions.keys()),
                t2_lock_symbols=None,
            )
            if not eligible:
                continue
            try:
                res = engine.evaluate(window, foreign_flow=None,
                                      market_context=macro_ctx)
            except Exception:
                continue
            if res.action == "BUY":
                pending_buys.append((sym, res.score, res.regime))

        # ─────────────────────────────────────────────────────
        # E) Mark-to-market equity
        # ─────────────────────────────────────────────────────
        mtm = 0.0
        for sym, pos in positions.items():
            df = market.get(sym)
            if df is None:
                continue
            # last known close ≤ date
            try:
                px = float(df.loc[:date, "close"].iloc[-1])
            except (KeyError, IndexError):
                px = pos.entry_price
            mtm += pos.qty * px
        equity_curve.append((date, cash + mtm))

    # ─────────────────────────────────────────────────────
    # Close remaining positions at last close
    # ─────────────────────────────────────────────────────
    if positions:
        last_date = equity_curve[-1][0] if equity_curve else all_dates[-1]
        for sym, pos in list(positions.items()):
            df = market.get(sym)
            if df is None:
                continue
            try:
                exit_p = float(df.loc[:last_date, "close"].iloc[-1])
            except (KeyError, IndexError):
                exit_p = pos.entry_price
            trades.append(TradeLog(
                symbol=sym,
                entry_date=pos.entry_date,
                exit_date=last_date,
                entry_price=pos.entry_price,
                exit_price=exit_p,
                quantity=pos.qty,
                net_pnl=_compute_trade_pnl(pos.entry_price, exit_p, pos.qty),
                exit_reason="EOD",
                holding_days=(last_date - pos.entry_date).days,
            ))
            cash += pos.qty * exit_p * (1 - _COMMISSION_RATE - _SLIPPAGE_RATE)
        positions.clear()

    return {
        "initial_cash": initial_cash,
        "final_cash": cash,
        "trades": trades,
        "equity_curve": equity_curve,
        "n_symbols": len(market),
        "max_positions": max_positions,
    }


# ─────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────
def _compute_aggregate_metrics(res: dict) -> dict:
    eq = res["equity_curve"]
    trades = res["trades"]
    if not eq:
        return {}
    series = pd.Series([v for _, v in eq], index=[d for d, _ in eq])
    returns = series.pct_change().dropna()
    total_return = (series.iloc[-1] - series.iloc[0]) / series.iloc[0]
    n_years = len(series) / _PERIODS_PER_YEAR
    cagr = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0.0

    sharpe = (returns.mean() / returns.std() * np.sqrt(_PERIODS_PER_YEAR)) if returns.std() > 0 else 0.0
    down = returns[returns < 0]
    down_std = float(np.sqrt((down ** 2).mean())) if not down.empty else 0.0
    sortino = (returns.mean() / down_std * np.sqrt(_PERIODS_PER_YEAR)) if down_std > 0 else 0.0

    peak, mdd = series.iloc[0], 0.0
    for v in series:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > mdd:
            mdd = dd

    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    gross_win = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))
    pf = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = -gross_loss / len(losses) if losses else 0.0

    hdays = [t.holding_days for t in trades] if trades else [0]
    avg_hold = float(np.mean(hdays))
    median_hold = float(np.median(hdays))

    exit_reasons = defaultdict(int)
    for t in trades:
        exit_reasons[t.exit_reason] += 1

    return {
        "total_return": float(total_return),
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "mdd": float(mdd),
        "win_rate": float(win_rate),
        "profit_factor": float(pf),
        "total_trades": len(trades),
        "trades_per_year": len(trades) / n_years if n_years > 0 else 0.0,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "avg_hold_days": avg_hold,
        "median_hold_days": median_hold,
        "exit_reasons": dict(exit_reasons),
        "n_years": n_years,
    }


def _periodic_returns(eq: list[tuple[pd.Timestamp, float]], freq: str) -> pd.Series:
    """freq: 'YE' for yearly, 'QE' for quarterly, 'ME' for monthly."""
    if not eq:
        return pd.Series(dtype=float)
    s = pd.Series([v for _, v in eq], index=pd.DatetimeIndex([d for d, _ in eq]))
    # last value each period
    resampled = s.resample(freq).last()
    # initial "period 0" value to compute first period return
    first = pd.Series([s.iloc[0]], index=[s.index[0] - pd.Timedelta(days=1)])
    joined = pd.concat([first, resampled]).sort_index()
    return joined.pct_change().dropna()


def _periodic_trades(trades: list[TradeLog], freq: str) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame([{
        "exit_date": t.exit_date,
        "net_pnl": t.net_pnl,
        "win": 1 if t.net_pnl > 0 else 0,
    } for t in trades])
    df.set_index("exit_date", inplace=True)
    g = df.resample(freq).agg(
        n_trades=("net_pnl", "size"),
        win_rate=("win", "mean"),
        pnl=("net_pnl", "sum"),
    )
    return g


# ─────────────────────────────────────────────────────────────────────
# Output writers
# ─────────────────────────────────────────────────────────────────────
def _write_trades_csv(trades: list[TradeLog], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "entry_date", "exit_date", "entry_price", "exit_price",
                    "qty", "net_pnl", "exit_reason", "holding_days"])
        for t in trades:
            w.writerow([
                t.symbol,
                t.entry_date.date(),
                t.exit_date.date(),
                round(t.entry_price, 2),
                round(t.exit_price, 2),
                t.quantity,
                round(t.net_pnl, 0),
                t.exit_reason,
                t.holding_days,
            ])


def _write_equity_csv(eq: list[tuple[pd.Timestamp, float]], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "equity"])
        for d, v in eq:
            w.writerow([d.date(), round(v, 0)])


def _write_periodic_csv(
    yearly: pd.Series, yearly_tr: pd.DataFrame,
    quarterly: pd.Series, quarterly_tr: pd.DataFrame,
    path: Path,
) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["period_type", "period", "return", "n_trades", "win_rate", "pnl"])
        for ts, ret in yearly.items():
            label = f"{ts.year}"
            tr = yearly_tr.loc[ts] if ts in yearly_tr.index else None
            w.writerow([
                "year", label, round(ret, 4),
                int(tr["n_trades"]) if tr is not None else 0,
                round(float(tr["win_rate"]), 4) if tr is not None else 0,
                round(float(tr["pnl"]), 0) if tr is not None else 0,
            ])
        for ts, ret in quarterly.items():
            label = f"{ts.year}Q{ts.quarter}"
            tr = quarterly_tr.loc[ts] if ts in quarterly_tr.index else None
            w.writerow([
                "quarter", label, round(ret, 4),
                int(tr["n_trades"]) if tr is not None else 0,
                round(float(tr["win_rate"]), 4) if tr is not None else 0,
                round(float(tr["pnl"]), 0) if tr is not None else 0,
            ])


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────
def main() -> None:
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    config_path = Path("config/config.json")
    config = json.loads(config_path.read_text())
    initial_cash = config["capital"]["initial"]
    max_positions = config["capital"].get("max_positions", 5)

    vn30 = _load_vn30()
    print(f"Running portfolio backtest: {len(vn30)} VN30 symbols, "
          f"initial={initial_cash:,.0f} VND, max_positions={max_positions}, 5 years")
    print(f"Symbols: {', '.join(vn30)}\n")

    res = run_portfolio(vn30, initial_cash=initial_cash,
                        max_positions=max_positions, years=5)

    metrics = _compute_aggregate_metrics(res)
    yearly  = _periodic_returns(res["equity_curve"], "YE")
    quarterly = _periodic_returns(res["equity_curve"], "QE")
    yearly_tr  = _periodic_trades(res["trades"], "YE")
    quarterly_tr = _periodic_trades(res["trades"], "QE")

    out = Path("data")
    out.mkdir(exist_ok=True)
    _write_trades_csv(res["trades"], out / "backtest_portfolio_vn30_trades.csv")
    _write_equity_csv(res["equity_curve"], out / "backtest_portfolio_vn30_equity.csv")
    _write_periodic_csv(yearly, yearly_tr, quarterly, quarterly_tr,
                        out / "backtest_portfolio_vn30_periodic.csv")

    # ── stdout ─────────────────────────────────────────────────────
    print("=== Aggregate (VN30 portfolio, 5 years) ===")
    print(f"Period           : {res['equity_curve'][0][0].date()} → "
          f"{res['equity_curve'][-1][0].date()} "
          f"({metrics['n_years']:.2f} yrs)")
    print(f"Initial capital  : {res['initial_cash']:>16,.0f} VND")
    print(f"Final equity     : {res['equity_curve'][-1][1]:>16,.0f} VND")
    print(f"Total return     : {metrics['total_return']:>+15.2%}")
    print(f"CAGR             : {metrics['cagr']:>+15.2%}")
    print(f"Sharpe           : {metrics['sharpe']:>15.3f}")
    print(f"Sortino          : {metrics['sortino']:>15.3f}")
    print(f"Max drawdown     : {metrics['mdd']:>15.2%}")
    print(f"Win rate         : {metrics['win_rate']:>15.2%}")
    print(f"Profit factor    : {metrics['profit_factor']:>15.3f}")
    print(f"Total trades     : {metrics['total_trades']:>15d} "
          f"({metrics['trades_per_year']:.1f}/year)")
    print(f"Avg win          : {metrics['avg_win']:>+15,.0f} VND")
    print(f"Avg loss         : {metrics['avg_loss']:>+15,.0f} VND")
    print(f"Avg hold days    : {metrics['avg_hold_days']:>15.1f}")
    print(f"Median hold days : {metrics['median_hold_days']:>15.1f}")
    print(f"Exit reasons     : {metrics['exit_reasons']}")

    print("\n=== Yearly returns ===")
    print(f"{'Year':<6} {'Return':>9} {'Trades':>8} {'WinRate':>8} {'PnL (M VND)':>13}")
    for ts, ret in yearly.items():
        tr = yearly_tr.loc[ts] if ts in yearly_tr.index else None
        n = int(tr["n_trades"]) if tr is not None else 0
        wr = float(tr["win_rate"]) if tr is not None else 0
        pnl = float(tr["pnl"]) / 1e6 if tr is not None else 0
        print(f"{ts.year:<6} {ret:>+8.2%} {n:>8d} {wr:>7.2%} {pnl:>+12.1f}")

    print("\n=== Quarterly returns ===")
    print(f"{'Period':<8} {'Return':>9} {'Trades':>8} {'WinRate':>8} {'PnL (M VND)':>13}")
    for ts, ret in quarterly.items():
        tr = quarterly_tr.loc[ts] if ts in quarterly_tr.index else None
        n = int(tr["n_trades"]) if tr is not None else 0
        wr = float(tr["win_rate"]) if tr is not None else 0
        pnl = float(tr["pnl"]) / 1e6 if tr is not None else 0
        print(f"{ts.year}Q{ts.quarter:<4} {ret:>+8.2%} {n:>8d} {wr:>7.2%} {pnl:>+12.1f}")

    print(f"\nWrote trades → data/backtest_portfolio_vn30_trades.csv")
    print(f"Wrote equity → data/backtest_portfolio_vn30_equity.csv")
    print(f"Wrote periodic → data/backtest_portfolio_vn30_periodic.csv")


if __name__ == "__main__":
    main()
