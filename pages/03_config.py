"""Trang 3: Config — bot params, data_source toggle, save/reset."""
from __future__ import annotations

import streamlit as st

from core.ui_helpers import load_config, save_config

st.set_page_config(page_title="Config — VN Auto Trading", layout="wide")
st.title("Bot Configuration")
st.caption("Changes are saved to `config/config.json`. Restart the bot to apply.")

config = load_config()

# ---------------------------------------------------------------------------
# Capital & Risk
# ---------------------------------------------------------------------------
st.subheader("Capital & Risk")
cap = config.get("capital", {})
risk = config.get("risk", {})

c1, c2 = st.columns(2)
with c1:
    initial_capital = st.number_input(
        "Initial Capital (VND)", value=int(cap.get("initial", 500_000_000)), step=10_000_000,
    )
    max_positions = st.number_input("Max Positions", value=int(cap.get("max_positions", 5)), min_value=1, max_value=20)
with c2:
    risk_pct = st.slider("Risk per Trade (%)", 0.5, 5.0, float(cap.get("risk_per_trade_pct", 0.02)) * 100, 0.1)
    max_pos_pct = st.slider("Max Position Size (%)", 5.0, 50.0, float(cap.get("max_position_pct", 0.20)) * 100, 1.0)

# ---------------------------------------------------------------------------
# Signal Settings
# ---------------------------------------------------------------------------
st.subheader("Signal Settings")
sig = config.get("signal", {})
sc1, sc2 = st.columns(2)
with sc1:
    min_score = st.slider("Min Score Threshold", 0.40, 0.80, float(sig.get("min_score", 0.55)), 0.01)
with sc2:
    min_vol_ma20 = st.number_input(
        "Min Volume MA20 (shares)", value=int(sig.get("min_volume_ma20", 100_000)), step=10_000,
    )

# ---------------------------------------------------------------------------
# Data Source
# ---------------------------------------------------------------------------
st.subheader("Data Source")
data_sources = ["YFINANCE", "SSI"]
current_ds = config.get("data_source", "YFINANCE")
data_source = st.radio("Data Source", data_sources, index=data_sources.index(current_ds), horizontal=True)
if data_source == "SSI":
    st.warning("SSI data source requires Phase 2 credentials. Make sure `SSI_TOKEN` env var is set.")

# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------
st.subheader("Mode")
modes = ["PAPER", "LIVE"]
current_mode = config.get("mode", "PAPER")
mode = st.radio("Trading Mode", modes, index=modes.index(current_mode), horizontal=True)
if mode == "LIVE":
    st.error("⚠️ LIVE mode executes real orders. Enable only after completing 60-day paper trade period.")

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
st.subheader("Telegram Notifications")
tg = config.get("telegram", {})
tc1, tc2, tc3 = st.columns([1, 2, 2])
tg_enabled = tc1.checkbox("Enabled", value=bool(tg.get("enabled", False)))
tg_token = tc2.text_input("Bot Token", value=tg.get("bot_token", ""), type="password")
tg_chat_id = tc3.text_input("Chat ID", value=tg.get("chat_id", ""))

# ---------------------------------------------------------------------------
# Save / Reset buttons
# ---------------------------------------------------------------------------
st.divider()
save_col, reset_col, _ = st.columns([1, 1, 4])

if save_col.button("💾 Save Config", type="primary"):
    config["capital"] = {
        "initial": initial_capital,
        "max_positions": max_positions,
        "risk_per_trade_pct": round(risk_pct / 100, 4),
        "max_position_pct": round(max_pos_pct / 100, 4),
    }
    config["signal"] = {"min_score": min_score, "min_volume_ma20": min_vol_ma20}
    config["data_source"] = data_source
    config["mode"] = mode
    config["telegram"] = {
        "enabled": tg_enabled,
        "bot_token": tg_token,
        "chat_id": tg_chat_id,
    }
    save_config(config)
    st.success("Config saved. Restart the bot to apply changes.")

if reset_col.button("↺ Reset to Saved"):
    st.rerun()
