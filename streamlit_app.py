"""
streamlit_app.py — Web dashboard (read-only from DB/JSON, writes config + signal_queue).
Run: streamlit run streamlit_app.py
"""
import streamlit as st

st.set_page_config(page_title="VN Auto Trading", layout="wide")

pages = {
    "Dashboard": "pages/01_dashboard.py",
    "Signal Queue": "pages/02_signals.py",
    "Config": "pages/03_config.py",
    "Reports": "pages/04_reports.py",
    "Backtest": "pages/05_backtest.py",
}

st.sidebar.title("VN Auto Trading")
st.sidebar.caption("Phase 1 — Paper Trading")

page = st.sidebar.radio("Navigate", list(pages.keys()))
st.info(f"Page '{page}' — coming soon. Run the bot first: `python trading_bot.py start`")
