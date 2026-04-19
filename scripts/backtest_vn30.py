"""
Backtest all VN30 symbols with 5-year window and export metrics to CSV.

Usage:
    python scripts/backtest_vn30.py
Output:
    data/backtest_vn30_2021-2026.csv
    Prints aggregate median/mean metrics to stdout.
"""
from __future__ import annotations

import csv
import json
import logging
import sys
from pathlib import Path
from statistics import mean, median

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.backtester import Backtester  # noqa: E402


def _load_vn30() -> list[str]:
    """Extract VN30 symbols from universe/HOSE.txt (between '# VN30' and next '#' section)."""
    path = Path("data/universe/HOSE.txt")
    symbols: list[str] = []
    in_vn30 = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped == "# VN30":
            in_vn30 = True
            continue
        if in_vn30:
            if stripped.startswith("#"):
                break
            if stripped:
                symbols.append(stripped)
    return symbols


def _load_config() -> dict:
    return json.loads(Path("config/config.json").read_text())


def main() -> None:
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    vn30 = _load_vn30()
    print(f"Loaded {len(vn30)} VN30 symbols: {', '.join(vn30)}\n")

    config = _load_config()
    bt = Backtester(config)

    out_path = Path("data/backtest_vn30_2021-2026.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []

    header = ["symbol", "total_return", "sharpe", "sortino", "mdd",
              "win_rate", "profit_factor", "trades", "trades_per_year",
              "avg_win", "avg_loss", "buy_hold", "alpha"]
    print(f"{'Symbol':<7} {'Return':>8} {'Sharpe':>7} {'MDD':>7} "
          f"{'WinRate':>8} {'PF':>5} {'Trades':>7} {'B&H':>8} {'Alpha':>8}")
    print("-" * 80)

    for sym in vn30:
        try:
            result = bt.run(symbols=[sym], years=5)
            m = result.in_sample
            row = {
                "symbol": sym,
                "total_return": round(m.total_return, 4),
                "sharpe": round(m.sharpe_ratio, 3),
                "sortino": round(m.sortino_ratio, 3),
                "mdd": round(m.max_drawdown, 4),
                "win_rate": round(m.win_rate, 4),
                "profit_factor": round(m.profit_factor, 3)
                                   if m.profit_factor != float("inf") else "inf",
                "trades": m.total_trades,
                "trades_per_year": round(m.trades_per_year, 1),
                "avg_win": round(m.avg_win, 0),
                "avg_loss": round(m.avg_loss, 0),
                "buy_hold": round(m.benchmark_return, 4) if m.benchmark_return is not None else None,
                "alpha": round(m.alpha, 4) if m.alpha is not None else None,
            }
            rows.append(row)
            print(f"{sym:<7} {m.total_return:>+7.2%} {m.sharpe_ratio:>7.2f} "
                  f"{m.max_drawdown:>6.2%} {m.win_rate:>7.2%} "
                  f"{m.profit_factor if m.profit_factor != float('inf') else 999:>5.2f} "
                  f"{m.total_trades:>7d} "
                  f"{(m.benchmark_return or 0):>+7.2%} {(m.alpha or 0):>+7.2%}")
        except Exception as exc:
            print(f"{sym:<7} ERROR: {exc}")

    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows → {out_path}")

    # ── Aggregate ─────────────────────────────────────────────────────────
    if not rows:
        return
    valid = [r for r in rows if isinstance(r["profit_factor"], float)]
    returns = [r["total_return"] for r in rows]
    sharpes = [r["sharpe"] for r in rows]
    mdds    = [r["mdd"] for r in rows]
    winrts  = [r["win_rate"] for r in rows if r["trades"] > 0]
    pfs     = [r["profit_factor"] for r in valid if r["trades"] > 0]
    trades  = [r["trades"] for r in rows]
    bhs     = [r["buy_hold"] for r in rows if r["buy_hold"] is not None]
    alphas  = [r["alpha"] for r in rows if r["alpha"] is not None]
    positive_alpha = sum(1 for a in alphas if a > 0)

    print("\n=== Aggregate (VN30, 5-year, 2021-2026) ===")
    print(f"Median total return : {median(returns):+.2%}")
    print(f"Mean total return   : {mean(returns):+.2%}")
    print(f"Median Sharpe       : {median(sharpes):.3f}")
    print(f"Median MDD          : {median(mdds):.2%}")
    print(f"Median win rate     : {median(winrts):.2%}" if winrts else "Median win rate     : n/a")
    print(f"Median profit factor: {median(pfs):.3f}" if pfs else "Median PF           : n/a")
    print(f"Total trades        : {sum(trades)}")
    print(f"Median buy & hold   : {median(bhs):+.2%}")
    print(f"Median alpha        : {median(alphas):+.2%}")
    print(f"Symbols with +alpha : {positive_alpha}/{len(alphas)}")


if __name__ == "__main__":
    main()
