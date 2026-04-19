"""Unit tests for TelegramNotifier (Week 8)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from integrations.telegram_bot import TelegramNotifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _notifier(enabled: bool = True) -> TelegramNotifier:
    return TelegramNotifier(bot_token="TOKEN", chat_id="CHAT", enabled=enabled)


def _mock_ok_response():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_telegram_notify_buy_signal_format():
    """notify_buy_signal → message contains symbol, score, price, and web link."""
    notifier = _notifier()
    with patch("requests.post", return_value=_mock_ok_response()) as mock_post:
        notifier.notify_buy_signal(
            symbol="VCB",
            score=0.72,
            price=85_000,
            web_url="http://localhost:8501",
        )
    mock_post.assert_called_once()
    payload = mock_post.call_args.kwargs["json"]
    text = payload["text"]
    assert "VCB" in text
    assert "+0.720" in text
    assert "85,000" in text
    assert "http://localhost:8501" in text


def test_telegram_notify_stop_loss_hit():
    """notify_stop_loss_hit → message contains symbol, exit price, and PnL."""
    notifier = _notifier()
    with patch("requests.post", return_value=_mock_ok_response()) as mock_post:
        notifier.notify_stop_loss_hit(symbol="HPG", exit_price=45_200, pnl=-320_000)
    payload = mock_post.call_args.kwargs["json"]
    text = payload["text"]
    assert "HPG" in text
    assert "45,200" in text
    assert "-320,000" in text


def test_telegram_notify_circuit_breaker():
    """notify_circuit_breaker → message contains MDD%, threshold, and STOPPED status."""
    notifier = _notifier()
    with patch("requests.post", return_value=_mock_ok_response()) as mock_post:
        notifier.notify_circuit_breaker(mdd_pct=0.32, threshold_pct=0.30)
    payload = mock_post.call_args.kwargs["json"]
    text = payload["text"]
    assert "32.0%" in text
    assert "30.0%" in text
    assert "STOPPED" in text


def test_telegram_notify_daily_summary_at_1600():
    """notify_daily_summary → correct format with date, num_trades, equity, pnl_pct."""
    notifier = _notifier()
    with patch("requests.post", return_value=_mock_ok_response()) as mock_post:
        notifier.notify_daily_summary(
            date="2026-04-20",
            num_trades=3,
            equity=510_000_000,
            pnl_pct=0.02,
        )
    payload = mock_post.call_args.kwargs["json"]
    text = payload["text"]
    assert "2026-04-20" in text
    assert "3" in text
    assert "510,000,000" in text
    assert "+2.00%" in text


def test_telegram_disabled_does_not_call_api():
    """When enabled=False, send_message returns True without HTTP call."""
    notifier = _notifier(enabled=False)
    with patch("requests.post") as mock_post:
        result = notifier.send_message("test")
    assert result is True
    mock_post.assert_not_called()


def test_telegram_from_config():
    """TelegramNotifier.from_config reads bot_token, chat_id, enabled from config dict."""
    config = {"telegram": {"bot_token": "T123", "chat_id": "C456", "enabled": True}}
    notifier = TelegramNotifier.from_config(config)
    assert notifier._token == "T123"
    assert notifier._chat_id == "C456"
    assert notifier._enabled is True
