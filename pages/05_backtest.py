"""Trang 5: Backtest — run backtest from UI, display results."""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Backtest — VN Auto Trading", layout="wide")
st.title("Backtest")

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
st.subheader("Parameters")
p1, p2, p3 = st.columns(3)
with p1:
    symbol = st.text_input("Symbol (e.g. VCB)", value="VCB").upper().strip()
    years = st.slider("History (years)", 1, 5, 3)
with p2:
    walk_forward = st.checkbox("Walk-forward (70/30 IS/OOS)", value=False)
    engine_name = st.selectbox("Signal Engine", ["MomentumV1"])
with p3:
    min_score = st.slider("Min Score", 0.40, 0.80, 0.55, 0.01)

run_btn = st.button("▶ Run Backtest", type="primary")

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if run_btn and symbol:
    with st.spinner(f"Running backtest on {symbol} ({years}y)…"):
        try:
            from datetime import date, timedelta

            import pandas as pd

            from core.backtester import Backtester
            from core.data_manager import DataManager
            from data_sources.yfinance_client import YFinanceClient

            dm = DataManager(YFinanceClient())
            backtester = Backtester(data_manager=dm)

            end = date.today().isoformat()
            start = (date.today() - timedelta(days=years * 365)).isoformat()

            metrics = backtester.run(
                symbol=symbol,
                start=start,
                end=end,
                walk_forward=walk_forward,
            )

            st.success("Backtest complete.")

            # ---------------------------------------------------------------------------
            # Results
            # ---------------------------------------------------------------------------
            st.subheader("Results")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Total Return", f"{metrics.total_return:.1%}")
            r2.metric("Sharpe Ratio", f"{metrics.sharpe:.2f}")
            r3.metric("Max Drawdown", f"{metrics.max_drawdown:.1%}")
            r4.metric("Win Rate", f"{metrics.win_rate:.1%}")

            r5, r6, r7, r8 = st.columns(4)
            r5.metric("Sortino", f"{metrics.sortino:.2f}")
            r6.metric("Profit Factor", f"{metrics.profit_factor:.2f}")
            r7.metric("Trades", metrics.num_trades)
            benchmark = getattr(metrics, "benchmark_return", None)
            if benchmark is not None:
                r8.metric("Alpha vs Benchmark", f"{metrics.total_return - benchmark:+.1%}")

            # Equity curve
            if hasattr(metrics, "equity_curve") and metrics.equity_curve:
                import pandas as pd
                st.subheader("Equity Curve")
                eq_df = pd.Series(metrics.equity_curve, name="NAV")
                st.line_chart(eq_df, use_container_width=True)

        except FileNotFoundError:
            st.error(f"No data for {symbol}. Run `python trading_bot.py init-data` first.")
        except Exception as exc:
            st.error(f"Backtest failed: {exc}")
elif run_btn and not symbol:
    st.warning("Enter a symbol first.")
