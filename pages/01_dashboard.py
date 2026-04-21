"""Trang 1: Dashboard — equity, positions, circuit breaker, equity curve."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from core.ui_helpers import (
    load_config,
    load_equity_history,
    load_portfolio,
)


def _load_latest_prices(db_path: Path = Path("data/trades.db")) -> tuple[dict[str, float], str]:
    """Read prices from the most recent monitor_logs entry written by the bot."""
    if not db_path.exists():
        return {}, ""
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT prices, run_at FROM monitor_logs "
                "WHERE prices != '{}' ORDER BY run_at DESC LIMIT 1"
            ).fetchone()
        if row:
            return json.loads(row[0] or "{}"), row[1]
    except Exception:
        pass
    return {}, ""

st.set_page_config(page_title="Dashboard — VN Auto Trading", layout="wide")
st.title("Dashboard")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
config = load_config()
portfolio = load_portfolio()
equity_history = load_equity_history()
latest_prices, prices_updated_at = _load_latest_prices()

cash: float = portfolio.get("cash", 0)
positions: dict = portfolio.get("positions", {})
initial_capital: float = config.get("capital", {}).get("initial", 500_000_000)

# ---------------------------------------------------------------------------
# Top metrics row
# ---------------------------------------------------------------------------
market_value = sum(
    p.get("qty", 0) * (latest_prices.get(sym, p.get("avg_price", 0)))
    for sym, p in positions.items()
)
nav = cash + market_value
total_return_pct = (nav - initial_capital) / initial_capital * 100 if initial_capital else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("NAV", f"{nav:,.0f} ₫", f"{total_return_pct:+.2f}%")
col2.metric("Cash", f"{cash:,.0f} ₫")
col3.metric("Market Value", f"{market_value:,.0f} ₫")
col4.metric("Positions", len(positions))

st.divider()

# ---------------------------------------------------------------------------
# Circuit breaker status
# ---------------------------------------------------------------------------
from core.risk_engine import RiskEngine  # noqa: E402

backtest_mdd = config.get("risk", {}).get("backtest_mdd", 0.10)
circuit_threshold = backtest_mdd * RiskEngine.CIRCUIT_MULT

# Compute current MDD from equity history
if equity_history:
    navs = [r["nav"] for r in equity_history]
    peak = navs[0]
    current_mdd = 0.0
    for v in navs:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        if dd > current_mdd:
            current_mdd = dd
else:
    current_mdd = 0.0

cb_pct = current_mdd / circuit_threshold * 100 if circuit_threshold > 0 else 0
cb_color = "🔴" if current_mdd >= circuit_threshold else ("🟡" if cb_pct > 70 else "🟢")

cb_col1, cb_col2 = st.columns([1, 3])
cb_col1.markdown(f"**Circuit Breaker** {cb_color}")
cb_col2.progress(
    min(cb_pct / 100, 1.0),
    text=f"MDD {current_mdd:.1%} / threshold {circuit_threshold:.1%}",
)

st.divider()

# ---------------------------------------------------------------------------
# Positions table
# ---------------------------------------------------------------------------
st.subheader("Open Positions")
if prices_updated_at:
    st.caption(f"Giá cập nhật lúc: {prices_updated_at[11:16]} (bot intraday job — mỗi 15p / cuối ngày)")
if positions:
    rows = []
    for sym, p in positions.items():
        avg = p.get("avg_price", 0)
        price = latest_prices.get(sym)
        if price and avg:
            pnl_pct = (price - avg) / avg * 100
            pnl_pct_str = f"{pnl_pct:+.2f}%"
            price_str = f"{price:,.0f}"
        else:
            price_str = "—"
            pnl_pct_str = "—"
        rows.append({
            "Symbol": sym,
            "Qty": p.get("qty", 0),
            "Avg Price": f"{avg:,.0f}",
            "Price": price_str,
            "P&L %": pnl_pct_str,
            "Stop Loss": f"{p.get('stop_loss', 0):,.0f}",
            "Take Profit": f"{p.get('take_profit', 0):,.0f}",
            "Trail": "✓" if p.get("trail_active") else "",
            "Buy Date": p.get("buy_date", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No open positions.")

st.divider()

# ---------------------------------------------------------------------------
# Equity curve
# ---------------------------------------------------------------------------
st.subheader("Equity Curve")
if equity_history:
    df_eq = pd.DataFrame(equity_history)
    df_eq["recorded_date"] = pd.to_datetime(df_eq["recorded_date"])
    df_eq = df_eq.set_index("recorded_date")
    st.line_chart(df_eq[["nav"]], use_container_width=True)
else:
    st.info("No equity history yet. Data is recorded at 15:10 each trading day.")
