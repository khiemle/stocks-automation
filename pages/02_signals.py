"""Trang 2: Signal Queue + Watchlist Manager."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.ui_helpers import (
    add_to_watchlist,
    approve_signal,
    load_config,
    load_queue,
    reject_signal,
    remove_from_watchlist,
)

st.set_page_config(page_title="Signals — VN Auto Trading", layout="wide")
st.title("Signal Queue & Watchlist")

tab_signals, tab_watchlist = st.tabs(["Signal Queue", "Watchlist"])

# ---------------------------------------------------------------------------
# Tab 1: Signal Queue
# ---------------------------------------------------------------------------
with tab_signals:
    signals = load_queue()

    status_filter = st.selectbox(
        "Filter by status",
        ["ALL", "PENDING", "APPROVED", "REJECTED", "EXPIRED", "ORDER_PLACED", "FILLED"],
        index=1,
    )

    filtered = signals if status_filter == "ALL" else [s for s in signals if s["status"] == status_filter]

    if not filtered:
        st.info(f"No signals with status '{status_filter}'.")
    else:
        for sig in filtered:
            status_icon = {
                "PENDING": "🟡",
                "APPROVED": "🟢",
                "REJECTED": "🔴",
                "EXPIRED": "⚫",
                "ORDER_PLACED": "🔵",
                "FILLED": "✅",
            }.get(sig["status"], "⚪")

            source_badge = f"[{sig.get('source', 'EOD')}]"

            with st.expander(
                f"{status_icon} {sig['symbol']} — {sig['action']}  score={sig['score']:.2f}  "
                f"{source_badge}  {sig.get('created_at', '')[:10]}",
                expanded=(sig["status"] == "PENDING"),
            ):
                ind = sig.get("indicators", {})
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Score", f"{sig['score']:.3f}")
                c2.metric("Stop Loss", f"{sig.get('stop_loss', 0):,.0f}")
                c3.metric("Take Profit", f"{sig.get('take_profit', 0):,.0f}")
                c4.metric("Engine", sig.get("engine", "—"))

                if ind:
                    with st.expander("Indicators"):
                        st.json(ind)

                if sig["status"] == "PENDING":
                    btn_col1, btn_col2, _ = st.columns([1, 1, 4])
                    if btn_col1.button("✅ Approve", key=f"approve_{sig['id']}"):
                        if approve_signal(sig["id"]):
                            st.success(f"Approved {sig['symbol']}")
                            st.rerun()
                        else:
                            st.error("Failed to approve — signal may have changed.")
                    if btn_col2.button("❌ Reject", key=f"reject_{sig['id']}"):
                        if reject_signal(sig["id"]):
                            st.warning(f"Rejected {sig['symbol']}")
                            st.rerun()
                        else:
                            st.error("Failed to reject.")

    st.caption(f"Total signals in queue: {len(signals)}")


# ---------------------------------------------------------------------------
# Tab 2: Watchlist Manager
# ---------------------------------------------------------------------------
with tab_watchlist:
    config = load_config()
    watchlist: list[str] = config.get("watchlist", [])

    st.subheader(f"Watchlist ({len(watchlist)}/10)")

    if watchlist:
        for sym in watchlist:
            wc1, wc2 = st.columns([4, 1])
            wc1.write(sym)
            if wc2.button("Remove", key=f"rm_{sym}"):
                remove_from_watchlist(sym)
                st.rerun()
    else:
        st.info("Watchlist is empty. Add symbols below.")

    st.divider()
    with st.form("add_watchlist_form"):
        new_sym = st.text_input("Add symbol (e.g. FPT)").upper().strip()
        submitted = st.form_submit_button("Add")
        if submitted and new_sym:
            try:
                add_to_watchlist(new_sym)
                st.success(f"Added {new_sym} to watchlist.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
