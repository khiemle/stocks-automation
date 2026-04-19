"""Trang 4: Reports — trade metrics, trade log, CSV export, benchmark."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from core.ui_helpers import compute_summary_metrics, load_equity_history, load_trades

st.set_page_config(page_title="Reports — VN Auto Trading", layout="wide")
st.title("Reports & Analytics")

trades = load_trades()
equity_history = load_equity_history()
metrics = compute_summary_metrics(trades)

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
st.subheader("Performance Summary")
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Total Trades", metrics["total_trades"])
m2.metric("Win Rate", f"{metrics['win_rate']:.1%}")
m3.metric("Profit Factor", f"{metrics['profit_factor']:.2f}" if metrics["profit_factor"] != float("inf") else "∞")
m4.metric("Net P&L", f"{metrics['total_net_pnl']:,.0f} ₫")
m5.metric("Avg Win", f"{metrics['avg_win']:,.0f} ₫")
m6.metric("Avg Loss", f"{metrics['avg_loss']:,.0f} ₫")

st.divider()

# ---------------------------------------------------------------------------
# Equity curve + drawdown
# ---------------------------------------------------------------------------
if equity_history:
    st.subheader("Equity Curve")
    df_eq = pd.DataFrame(equity_history)
    df_eq["recorded_date"] = pd.to_datetime(df_eq["recorded_date"])
    df_eq = df_eq.set_index("recorded_date")

    eq_col, dd_col = st.columns(2)
    with eq_col:
        st.line_chart(df_eq[["nav"]], use_container_width=True)
    with dd_col:
        peak = df_eq["nav"].cummax()
        drawdown = (df_eq["nav"] - peak) / peak
        st.area_chart(drawdown, use_container_width=True, color="#ff4444")
        st.caption("Drawdown (%)")

    st.divider()

# ---------------------------------------------------------------------------
# Trade log
# ---------------------------------------------------------------------------
st.subheader("Trade Log")
if trades:
    df_trades = pd.DataFrame(trades)
    df_trades["net_pnl"] = df_trades["net_pnl"].map(lambda x: f"{x:,.0f}")
    df_trades["gross_pnl"] = df_trades["gross_pnl"].map(lambda x: f"{x:,.0f}")
    df_trades["entry_price"] = df_trades["entry_price"].map(lambda x: f"{x:,.0f}")
    df_trades["exit_price"] = df_trades["exit_price"].map(lambda x: f"{x:,.0f}")

    st.dataframe(
        df_trades[["symbol", "quantity", "entry_price", "exit_price",
                   "entry_date", "exit_date", "gross_pnl", "net_pnl", "engine"]],
        use_container_width=True,
        hide_index=True,
    )

    # CSV export
    raw_df = pd.DataFrame(trades)
    csv_bytes = raw_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇ Export CSV",
        data=csv_bytes,
        file_name="trades_export.csv",
        mime="text/csv",
    )
else:
    st.info("No closed trades yet.")

# ---------------------------------------------------------------------------
# Per-symbol breakdown
# ---------------------------------------------------------------------------
if trades:
    st.divider()
    st.subheader("P&L by Symbol")
    df_raw = pd.DataFrame(trades)
    by_sym = (
        df_raw.groupby("symbol")
        .agg(trades=("net_pnl", "count"), net_pnl=("net_pnl", "sum"),
             win_rate=("net_pnl", lambda x: (x > 0).mean()))
        .reset_index()
        .sort_values("net_pnl", ascending=False)
    )
    st.dataframe(by_sym, use_container_width=True, hide_index=True)
