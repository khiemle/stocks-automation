"""Trang 2: Signal Queue + Watchlist Manager + Monitor Logs."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

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

tab_signals, tab_watchlist, tab_logs = st.tabs(["Signal Queue", "Watchlist", "Monitor Logs"])

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


# ---------------------------------------------------------------------------
# Tab 3: Monitor Logs
# ---------------------------------------------------------------------------
with tab_logs:
    _DB_PATH = Path("data/trades.db")

    def _load_monitor_logs(limit: int = 100) -> list[dict]:
        if not _DB_PATH.exists():
            return []
        try:
            with sqlite3.connect(_DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT run_at, run_type, positions_checked, stops_hit, tps_hit, "
                    "trails_updated, new_signals, prices "
                    "FROM monitor_logs ORDER BY run_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            result = []
            for r in rows:
                result.append({
                    "run_at": r[0],
                    "run_type": r[1],
                    "positions_checked": r[2],
                    "stops_hit": json.loads(r[3] or "[]"),
                    "tps_hit": json.loads(r[4] or "[]"),
                    "trails_updated": json.loads(r[5] or "[]"),
                    "new_signals": json.loads(r[6] or "[]"),
                    "prices": json.loads(r[7] or "{}"),
                })
            return result
        except Exception as e:
            st.error(f"Failed to load logs: {e}")
            return []

    col_filter, col_refresh = st.columns([3, 1])
    with col_filter:
        log_type_filter = st.selectbox("Run type", ["ALL", "INTRADAY", "EOD"], key="log_type")
    with col_refresh:
        st.write("")
        if st.button("🔄 Refresh", key="refresh_logs"):
            st.rerun()

    logs = _load_monitor_logs(limit=200)
    if log_type_filter != "ALL":
        logs = [l for l in logs if l["run_type"] == log_type_filter]

    if not logs:
        st.info("Chưa có log nào. Bot cần chạy ít nhất 1 chu kỳ intraday.")
    else:
        st.caption(f"{len(logs)} log entries (newest first)")
        for log in logs:
            has_events = any(log[k] for k in ("stops_hit", "tps_hit", "trails_updated", "new_signals"))
            time_str = log["run_at"][11:16] if len(log["run_at"]) >= 16 else log["run_at"]
            date_str = log["run_at"][:10]
            type_icon = "📅" if log["run_type"] == "EOD" else "🔄"
            event_badge = "⚠️ " if has_events else ""
            label = (
                f"{type_icon} {event_badge}{date_str} {time_str} — "
                f"{log['run_type']} — {log['positions_checked']} position(s)"
            )

            with st.expander(label, expanded=has_events):
                prices = log["prices"]
                if prices:
                    st.markdown("**Giá tại thời điểm chạy**")
                    price_cols = st.columns(min(len(prices), 4))
                    for i, (sym, price) in enumerate(prices.items()):
                        price_cols[i % 4].metric(sym, f"{price:,.0f}")

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Stops hit", len(log["stops_hit"]))
                c2.metric("TPs hit", len(log["tps_hit"]))
                c3.metric("Trail updates", len(log["trails_updated"]))
                c4.metric("New signals", len(log["new_signals"]))

                if log["stops_hit"]:
                    st.error("🛑 **Stop loss hit**")
                    for e in log["stops_hit"]:
                        st.write(f"  {e['symbol']}  @ {e['price']:,.0f}  P&L {e['pnl']:+,.0f} VND")

                if log["tps_hit"]:
                    st.success("🎯 **Take profit hit**")
                    for e in log["tps_hit"]:
                        st.write(f"  {e['symbol']}  @ {e['price']:,.0f}  P&L {e['pnl']:+,.0f} VND")

                if log["trails_updated"]:
                    st.info("🔼 **Trail stop updated**")
                    for e in log["trails_updated"]:
                        st.write(
                            f"  {e['symbol']}  price {e['price']:,.0f}  "
                            f"stop {e['old_stop']:,.0f} → {e['new_stop']:,.0f}"
                        )

                if log["new_signals"]:
                    st.warning(f"🟢 **New intraday signals**: {', '.join(log['new_signals'])}")

                if not has_events:
                    st.success("✅ All clear — không có sự kiện")
