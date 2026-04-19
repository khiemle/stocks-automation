"""Unit tests for Streamlit UI helper functions (Week 7)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_queue(path: Path, signals: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(signals))


def _pending_signal(symbol: str = "VCB") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "action": "BUY",
        "score": 0.70,
        "engine": "MomentumV1",
        "source": "EOD",
        "created_at": "2026-04-19T15:35:00",
        "stop_loss": 47_500,
        "take_profit": 54_500,
        "indicators": {},
        "status": "PENDING",
    }


# ---------------------------------------------------------------------------
# Signal queue tests
# ---------------------------------------------------------------------------

def test_approve_signal_updates_status_to_approved(tmp_path):
    """approve_signal() → status APPROVED được ghi vào file."""
    from core.ui_helpers import approve_signal

    queue_path = tmp_path / "signal_queue.json"
    sig = _pending_signal()
    _write_queue(queue_path, [sig])

    result = approve_signal(sig["id"], path=queue_path)

    assert result is True
    saved = json.loads(queue_path.read_text())
    assert saved[0]["status"] == "APPROVED"


def test_reject_signal_updates_status_to_rejected(tmp_path):
    """reject_signal() → status REJECTED được ghi vào file."""
    from core.ui_helpers import reject_signal

    queue_path = tmp_path / "signal_queue.json"
    sig = _pending_signal("HPG")
    _write_queue(queue_path, [sig])

    result = reject_signal(sig["id"], path=queue_path)

    assert result is True
    saved = json.loads(queue_path.read_text())
    assert saved[0]["status"] == "REJECTED"


def test_approve_returns_false_for_nonexistent_id(tmp_path):
    """approve_signal() với ID không tồn tại → return False, file không thay đổi."""
    from core.ui_helpers import approve_signal

    queue_path = tmp_path / "signal_queue.json"
    sig = _pending_signal()
    _write_queue(queue_path, [sig])

    result = approve_signal("nonexistent-id", path=queue_path)

    assert result is False
    saved = json.loads(queue_path.read_text())
    assert saved[0]["status"] == "PENDING"


# ---------------------------------------------------------------------------
# Watchlist tests
# ---------------------------------------------------------------------------

def test_add_to_watchlist_saves_to_config(tmp_path):
    """add_to_watchlist() → symbol xuất hiện trong config.json watchlist."""
    from core.ui_helpers import add_to_watchlist, load_config

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"watchlist": []}))

    add_to_watchlist("FPT", config_path=cfg_path)

    config = load_config(cfg_path)
    assert "FPT" in config["watchlist"]


def test_watchlist_max_10_enforced(tmp_path):
    """add_to_watchlist() khi đã có 10 mã → raise ValueError."""
    from core.ui_helpers import add_to_watchlist

    cfg_path = tmp_path / "config.json"
    existing = [f"SYM{i:02d}" for i in range(10)]
    cfg_path.write_text(json.dumps({"watchlist": existing}))

    with pytest.raises(ValueError, match="full"):
        add_to_watchlist("NEW01", config_path=cfg_path)


def test_save_config_persists_all_fields(tmp_path):
    """save_config() → reload → tất cả fields giữ nguyên."""
    from core.ui_helpers import load_config, save_config

    cfg_path = tmp_path / "config.json"
    original = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal": {"min_score": 0.55},
        "watchlist": ["VCB", "HPG"],
        "mode": "PAPER",
    }
    save_config(original, path=cfg_path)
    reloaded = load_config(cfg_path)

    assert reloaded == original


def test_streamlit_reads_only_no_api_call(tmp_path):
    """load_portfolio() và load_trades() không trigger network calls."""
    from unittest.mock import patch

    from core.ui_helpers import load_portfolio, load_trades

    portfolio_path = tmp_path / "portfolio.json"
    portfolio_path.write_text(json.dumps({
        "cash": 490_000_000,
        "equity_week_start": 500_000_000,
        "week_start_date": "2026-04-14",
        "positions": {},
    }))

    with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
        portfolio = load_portfolio(portfolio_path)
        trades = load_trades(tmp_path / "nonexistent.db")

    mock_get.assert_not_called()
    mock_post.assert_not_called()
    assert portfolio["cash"] == 490_000_000
    assert trades == []
