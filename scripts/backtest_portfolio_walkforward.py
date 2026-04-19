"""
Walk-forward portfolio backtest — IS/OOS split 70/30 trên VN30.

Dùng để validate rằng các cải tiến roadmap không overfit trên toàn bộ lịch sử.
Metric success: IS/OOS Sharpe lệch < 0.3 (mục tiêu roadmap 3.7).

Outputs:
    data/backtest_portfolio_wf_is_trades.csv
    data/backtest_portfolio_wf_oos_trades.csv
    data/backtest_portfolio_wf_is_equity.csv
    data/backtest_portfolio_wf_oos_equity.csv
    stdout: IS/OOS aggregate comparison
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.backtest_portfolio_vn30 import (  # noqa: E402
    _compute_aggregate_metrics,
    _load_vn30,
    _write_equity_csv,
    _write_trades_csv,
    run_portfolio,
)

_WARMUP = 252


def _split_market_data(years: int = 5, split: float = 0.70) -> tuple[int, int]:
    """Return (is_years, oos_years) as integer year counts (rounded)."""
    is_years = round(years * split, 1)
    oos_years = round(years - is_years, 1)
    return is_years, oos_years


def run_walkforward(
    symbols: list[str],
    initial_cash: float = 500_000_000,
    max_positions: int = 5,
    years: int = 5,
    split: float = 0.70,
) -> tuple[dict, dict]:
    """
    Run IS and OOS portfolio backtests with 70/30 date split.

    OOS window is prepended with warmup bars from end of IS to keep
    EMA200 calibrated — same logic as per-symbol walk-forward.
    Returns (is_result, oos_result).
    """
    from core.data_manager import DataManager
    from data_sources.yfinance_client import YFinanceClient
    from brokers.simulated_broker import _COMMISSION_RATE, _SLIPPAGE_RATE  # noqa: F401
    from core.market_regime import MarketRegime
    from core.risk_engine import RiskEngine
    from core.sector_map import can_add_to_sector
    from signals.momentum_v1 import MomentumV1
    from ta.volatility import AverageTrueRange
    from scripts.backtest_portfolio_vn30 import (
        Position, TradeLog, _load_market, _compute_trade_pnl,
        _WARMUP as WARMUP,
    )

    # Load full data for each symbol
    market_full: dict[str, pd.DataFrame] = {}
    for s in symbols:
        df = _load_market(s, years)
        if df is not None and len(df) >= WARMUP + 60:
            market_full[s] = df

    if not market_full:
        raise RuntimeError("No market data loaded")

    # Union of all dates
    all_dates_set: set[pd.Timestamp] = set()
    for df in market_full.values():
        all_dates_set.update(df.index)
    all_dates = pd.DatetimeIndex(sorted(all_dates_set))

    # Split date index 70/30
    total = len(all_dates)
    is_end_idx = int(total * split)
    is_dates = all_dates[:is_end_idx]
    # OOS: prepend warmup rows so indicators are calibrated
    oos_start_idx = max(0, is_end_idx - WARMUP)
    oos_dates = all_dates[oos_start_idx:]

    is_split_date = is_dates[-1]
    oos_split_date = oos_dates[WARMUP] if len(oos_dates) > WARMUP else oos_dates[0]

    print(f"IS period  : {is_dates[0].date()} → {is_split_date.date()} "
          f"({len(is_dates)} days, {len(is_dates)/252:.2f} yrs)")
    print(f"OOS period : {oos_split_date.date()} → {oos_dates[-1].date()} "
          f"({len(oos_dates) - WARMUP} days, {(len(oos_dates) - WARMUP)/252:.2f} yrs)\n")

    # Slice market data
    def _slice(df: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
        return df[df.index.isin(dates)]

    market_is  = {s: _slice(df, is_dates)  for s, df in market_full.items()}
    market_oos = {s: _slice(df, oos_dates) for s, df in market_full.items()}
    # Remove empty slices
    market_is  = {s: df for s, df in market_is.items()  if len(df) >= WARMUP + 20}
    market_oos = {s: df for s, df in market_oos.items() if len(df) >= WARMUP + 20}

    # Re-use run_portfolio but with pre-sliced market data by monkey-patching _load_market
    # Simpler: just call run_portfolio with is/oos year counts mapped to data slices.
    # Cleanest: rebuild run_portfolio using the sliced market dict directly.
    # We do that by computing year counts proportional to slice sizes.
    is_years  = max(1, round(len(is_dates)  / 252))
    oos_years = max(1, round((len(oos_dates) - WARMUP) / 252))

    def _run_on_slice(mkt: dict[str, pd.DataFrame], cap: float) -> dict:
        """Run portfolio engine on pre-loaded market slice."""
        from scripts.backtest_portfolio_vn30 import (
            _compute_trade_pnl, _WARMUP as WU, _MAX_SECTOR_POSITIONS,
        )
        from brokers.simulated_broker import _COMMISSION_RATE as CR, _SLIPPAGE_RATE as SR

        atr_cache: dict[str, pd.Series] = {}
        for s, df in mkt.items():
            atr_cache[s] = AverageTrueRange(
                df["high"], df["low"], df["close"], window=14
            ).average_true_range()

        all_d_set: set[pd.Timestamp] = set()
        for df in mkt.values():
            all_d_set.update(df.index)
        all_d = pd.DatetimeIndex(sorted(all_d_set))

        cash = cap
        positions: dict[str, Position] = {}
        trades: list[TradeLog] = []
        equity_curve: list[tuple[pd.Timestamp, float]] = []
        pending_buys: list[tuple[str, float, str]] = []
        pending_sells: set[str] = set()

        engine = MomentumV1()
        risk = RiskEngine(backtest_mdd=0.20, capital=cap)
        regime = MarketRegime(symbols=list(mkt.keys()))
        n_dates = len(all_d)

        from scripts.backtest_portfolio_vn30 import (
            _compute_trade_pnl as _pnl, TradeLog as TL, Position as POS,
        )

        for idx in range(WU, n_dates):
            date = all_d[idx]

            # A) Fill pending SELLs
            to_remove: list[str] = []
            for sym in list(pending_sells):
                if sym not in positions:
                    to_remove.append(sym)
                    continue
                pos = positions[sym]
                bd = len(pd.bdate_range(pos.entry_date, date)) - 1
                if bd < 2:
                    continue
                df = mkt.get(sym)
                if df is None or date not in df.index:
                    continue
                open_p = float(df.loc[date, "open"])
                proceeds = pos.qty * open_p * (1 - CR - SR)
                cash += proceeds
                trades.append(TL(sym, pos.entry_date, date, pos.entry_price, open_p,
                                 pos.qty, _pnl(pos.entry_price, open_p, pos.qty),
                                 "SELL", (date - pos.entry_date).days))
                del positions[sym]
                to_remove.append(sym)
            for s in to_remove:
                pending_sells.discard(s)

            # B) Fill pending BUYs
            slots = max_positions - len(positions)
            if slots > 0 and pending_buys:
                pending_buys.sort(key=lambda x: -x[1])
                for sym, score, er in pending_buys:
                    if slots <= 0:
                        break
                    if sym in positions:
                        continue
                    if not can_add_to_sector(sym, list(positions.keys()), _MAX_SECTOR_POSITIONS):
                        continue
                    df = mkt.get(sym)
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
                    risk_budget = cash * risk.RISK_PCT
                    max_by_cap = cash * risk.MAX_POSITION_PCT / open_p
                    raw_shares = min(risk_budget / stop_dist, max_by_cap)
                    qty = int(raw_shares // 100 * 100)
                    if qty < 100:
                        continue
                    cost = qty * open_p * (1 + CR + SR)
                    if cost > cash:
                        max_qty = int((cash / (open_p * (1 + CR + SR))) // 100 * 100)
                        if max_qty < 100:
                            continue
                        qty = max_qty
                        cost = qty * open_p * (1 + CR + SR)
                    tp = (open_p + 2.0 * atr_v if er == "SIDEWAYS"
                          else open_p + 1.5 * atr_v if er == "VOLATILE"
                          else None)
                    cash -= cost
                    positions[sym] = POS(sym, qty, open_p,
                                         open_p - risk.ATR_STOP_MULT * atr_v,
                                         atr_v, date, idx, take_profit=tp, entry_regime=er)
                    slots -= 1
            pending_buys = []

            # C) Intraday stop/trail/TP (T+2)
            to_close: list[tuple[str, float, str]] = []
            for sym, pos in positions.items():
                if idx <= pos.entry_idx:
                    continue
                bd = len(pd.bdate_range(pos.entry_date, date)) - 1
                if bd < 2:
                    continue
                df = mkt.get(sym)
                if df is None or date not in df.index:
                    continue
                bar = df.loc[date]
                lo, hi = float(bar["low"]), float(bar["high"])
                if lo <= pos.stop:
                    to_close.append((sym, pos.stop, "TRAIL" if pos.trail_active else "STOP"))
                    continue
                if pos.take_profit is not None and hi >= pos.take_profit:
                    to_close.append((sym, pos.take_profit, "TP"))
                    continue
                trigger = pos.entry_price + risk.ATR_TRAIL_TRIGGER * pos.entry_atr
                if not pos.trail_active and hi >= trigger:
                    pos.trail_active = True
                    pos.stop = max(pos.stop, pos.entry_price)
                if pos.trail_active:
                    ns = hi - risk.ATR_TRAIL_MULT * pos.entry_atr
                    if ns > pos.stop:
                        pos.stop = ns
            for sym, ep, reason in to_close:
                pos = positions[sym]
                cash += pos.qty * ep * (1 - CR - SR)
                trades.append(TL(sym, pos.entry_date, date, pos.entry_price, ep,
                                 pos.qty, _pnl(pos.entry_price, ep, pos.qty),
                                 reason, (date - pos.entry_date).days))
                del positions[sym]

            # D) Generate signals
            macro_ctx = regime.context(date)
            portfolio_full = len(positions) >= max_positions
            for sym, df in mkt.items():
                if date not in df.index:
                    continue
                window_end = df.index.get_loc(date)
                if window_end < WU:
                    continue
                window = df.iloc[: window_end + 1]
                if sym in positions:
                    try:
                        res = engine.evaluate(window, foreign_flow=None,
                                              market_context=macro_ctx)
                    except Exception:
                        continue
                    if res.action == "SELL":
                        pending_sells.add(sym)
                    continue
                if portfolio_full and len(pending_buys) >= max_positions:
                    continue
                eligible, _ = engine.is_eligible(window, sym,
                                                  portfolio_symbols=list(positions.keys()))
                if not eligible:
                    continue
                try:
                    res = engine.evaluate(window, foreign_flow=None,
                                          market_context=macro_ctx)
                except Exception:
                    continue
                if res.action == "BUY":
                    pending_buys.append((sym, res.score, res.regime))

            # E) Mark-to-market
            mtm = 0.0
            for sym, pos in positions.items():
                df = mkt.get(sym)
                if df is None:
                    continue
                try:
                    px = float(df.loc[:date, "close"].iloc[-1])
                except (KeyError, IndexError):
                    px = pos.entry_price
                mtm += pos.qty * px
            equity_curve.append((date, cash + mtm))

        # Close remaining
        if positions:
            last_date = equity_curve[-1][0] if equity_curve else all_d[-1]
            for sym, pos in list(positions.items()):
                df = mkt.get(sym)
                if df is None:
                    continue
                try:
                    exit_p = float(df.loc[:last_date, "close"].iloc[-1])
                except (KeyError, IndexError):
                    exit_p = pos.entry_price
                trades.append(TL(sym, pos.entry_date, last_date, pos.entry_price,
                                  exit_p, pos.qty, _pnl(pos.entry_price, exit_p, pos.qty),
                                  "EOD", (last_date - pos.entry_date).days))
                cash += pos.qty * exit_p * (1 - CR - SR)

        return {
            "initial_cash": cap,
            "final_cash": cash,
            "trades": trades,
            "equity_curve": equity_curve,
            "n_symbols": len(mkt),
            "max_positions": max_positions,
        }

    print("Running IS backtest...")
    is_result  = _run_on_slice(market_is,  initial_cash)
    print("Running OOS backtest...")
    oos_result = _run_on_slice(market_oos, initial_cash)
    return is_result, oos_result


def _print_comparison(is_m: dict, oos_m: dict) -> None:
    sharpe_delta = abs(is_m["sharpe"] - oos_m["sharpe"])
    print("\n=== Walk-forward comparison (IS vs OOS) ===")
    print(f"{'Metric':<20} {'IS':>10} {'OOS':>10} {'|Δ|':>8}")
    print("-" * 52)
    for key, label in [
        ("total_return", "Total return"),
        ("cagr", "CAGR"),
        ("sharpe", "Sharpe"),
        ("sortino", "Sortino"),
        ("mdd", "MDD"),
        ("win_rate", "Win rate"),
        ("profit_factor", "PF"),
    ]:
        iv = is_m.get(key, 0.0)
        ov = oos_m.get(key, 0.0)
        delta = abs(iv - ov)
        print(f"{label:<20} {iv:>+9.3f} {ov:>+9.3f} {delta:>8.3f}")
    print("-" * 52)
    status = "✅ PASS" if sharpe_delta < 0.3 else "❌ FAIL (> 0.3)"
    print(f"Sharpe IS/OOS delta: {sharpe_delta:.3f}  {status}")
    print(f"IS  trades: {is_m['total_trades']}  OOS trades: {oos_m['total_trades']}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    config_path = Path("config/config.json")
    config = json.loads(config_path.read_text())
    initial_cash = config["capital"]["initial"]
    max_positions = config["capital"].get("max_positions", 5)

    vn30 = _load_vn30()
    print(f"Walk-forward backtest: {len(vn30)} VN30 symbols, "
          f"initial={initial_cash:,.0f} VND, split=70/30\n")

    is_res, oos_res = run_walkforward(vn30, initial_cash=initial_cash,
                                      max_positions=max_positions)

    is_m  = _compute_aggregate_metrics(is_res)
    oos_m = _compute_aggregate_metrics(oos_res)

    _print_comparison(is_m, oos_m)

    out = Path("data")
    out.mkdir(exist_ok=True)
    _write_trades_csv(is_res["trades"],  out / "backtest_portfolio_wf_is_trades.csv")
    _write_trades_csv(oos_res["trades"], out / "backtest_portfolio_wf_oos_trades.csv")
    _write_equity_csv(is_res["equity_curve"],  out / "backtest_portfolio_wf_is_equity.csv")
    _write_equity_csv(oos_res["equity_curve"], out / "backtest_portfolio_wf_oos_equity.csv")
    print("\nWrote IS/OOS trades + equity CSVs to data/")


if __name__ == "__main__":
    main()
