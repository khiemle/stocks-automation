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
    symbol = st.text_input("Symbol (e.g. VCB, or ALL for full universe)", value="VCB").upper().strip()
    years = st.slider("History (years)", 1, 5, 3)
with p2:
    walk_forward = st.checkbox("Walk-forward (70/30 IS/OOS)", value=False)
with p3:
    st.markdown("**Engine:** MomentumV1 (fixed)")
    st.caption("Signal engine is set in Config page.")

run_btn = st.button("▶ Run Backtest", type="primary")

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if run_btn and symbol:
    is_all = symbol == "ALL"
    label = "full universe" if is_all else symbol

    with st.spinner(f"Running backtest on {label} ({years}y)…"):
        try:
            from core.backtester import Backtester
            from core.ui_helpers import load_config

            config = load_config()
            backtester = Backtester(config=config)

            if is_all:
                result = backtester.run_all(walk_forward=walk_forward)
            else:
                result = backtester.run(symbols=[symbol], years=years)

            st.success("Backtest complete.")

            # ---------------------------------------------------------------------------
            # In-sample results
            # ---------------------------------------------------------------------------
            def _show_metrics(label: str, m) -> None:
                st.subheader(label)
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Total Return", f"{m.total_return:.1%}")
                r2.metric("Sharpe Ratio", f"{m.sharpe_ratio:.2f}")
                r3.metric("Max Drawdown", f"{m.max_drawdown:.1%}")
                r4.metric("Win Rate", f"{m.win_rate:.1%}")

                r5, r6, r7, r8 = st.columns(4)
                r5.metric("Sortino", f"{m.sortino_ratio:.2f}")
                r6.metric("Profit Factor", f"{m.profit_factor:.2f}")
                r7.metric("Trades", m.num_trades)
                if m.alpha is not None:
                    r8.metric("Alpha vs Benchmark", f"{m.alpha:+.1%}")

            _show_metrics("In-Sample Results", result.in_sample)

            if result.out_of_sample is not None:
                st.divider()
                _show_metrics("Out-of-Sample Results", result.out_of_sample)

            # Equity curve
            if result.trades:
                import pandas as pd
                st.divider()
                st.subheader("Trade P&L Distribution")
                pnl_series = pd.Series([t.net_pnl for t in result.trades], name="Net P&L")
                st.bar_chart(pnl_series, use_container_width=True)

        except FileNotFoundError:
            st.error(f"No data for {symbol}. Run `python trading_bot.py init-data` first.")
        except Exception as exc:
            st.error(f"Backtest failed: {exc}")

elif run_btn and not symbol:
    st.warning("Enter a symbol first.")
