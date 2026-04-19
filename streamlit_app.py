"""
streamlit_app.py — Entry point for VN Auto Trading dashboard.
Run: streamlit run streamlit_app.py

Architecture:
  - Read-only from data/trades.db, data/portfolio.json, data/equity_history
  - Writes to config/config.json (params) and state/signal_queue.json (approve/reject)
  - Never calls broker API or data source directly
"""
import streamlit as st

st.set_page_config(
    page_title="VN Auto Trading",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("📈 VN Auto Trading")
st.sidebar.caption("Phase 1 — Paper Trading")
st.sidebar.divider()

from core.ui_helpers import load_config, load_portfolio  # noqa: E402

config = load_config()
portfolio = load_portfolio()
mode = config.get("mode", "PAPER")
mode_color = "🟢" if mode == "PAPER" else "🔴"

st.sidebar.markdown(f"**Mode:** {mode_color} {mode}")
st.sidebar.markdown(f"**Data:** {config.get('data_source', '—')}")

cash = portfolio.get("cash", 0)
n_positions = len(portfolio.get("positions", {}))
st.sidebar.markdown(f"**Cash:** {cash:,.0f} ₫")
st.sidebar.markdown(f"**Positions:** {n_positions}")

st.sidebar.divider()
st.sidebar.caption("Navigate via the pages sidebar (↑ above)")

# ---------------------------------------------------------------------------
# Home page content
# ---------------------------------------------------------------------------
st.title("VN Auto Trading — Dashboard")
st.markdown("""
Use the sidebar to navigate between pages:

| Page | Purpose |
|------|---------|
| **Dashboard** | Equity, open positions, circuit breaker, equity curve |
| **Signals** | Approve / reject EOD + intraday signals; manage watchlist |
| **Config** | Bot parameters, data source, trading mode |
| **Reports** | Trade log, performance metrics, CSV export |
| **Backtest** | Run backtests on individual symbols from the UI |
""")

# Quick status
from core.ui_helpers import load_queue  # noqa: E402

pending = [s for s in load_queue() if s["status"] == "PENDING"]
if pending:
    st.warning(f"⚠️ {len(pending)} pending signal(s) awaiting approval — go to **Signals** page.")
else:
    st.success("No pending signals.")
