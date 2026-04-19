"""Trang 1: Dashboard — equity, positions, circuit breaker, equity curve."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.ui_helpers import (
    load_config,
    load_equity_history,
    load_portfolio,
)

st.set_page_config(page_title="Dashboard — VN Auto Trading", layout="wide")
st.title("Dashboard")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
config = load_config()
portfolio = load_portfolio()
equity_history = load_equity_history()

cash: float = portfolio.get("cash", 0)
positions: dict = portfolio.get("positions", {})
initial_capital: float = config.get("capital", {}).get("initial", 500_000_000)

# ---------------------------------------------------------------------------
# Top metrics row
# ---------------------------------------------------------------------------
market_value = sum(p.get("qty", 0) * p.get("avg_price", 0) for p in positions.values())
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
if positions:
    rows = []
    for sym, p in positions.items():
        rows.append({
            "Symbol": sym,
            "Qty": p.get("qty", 0),
            "Avg Price": f"{p.get('avg_price', 0):,.0f}",
            "Stop Loss": f"{p.get('stop_loss', 0):,.0f}",
            "Take Profit": f"{p.get('take_profit', 0):,.0f}",
            "Trail Active": "✓" if p.get("trail_active") else "",
            "Engine": p.get("engine", ""),
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
