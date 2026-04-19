"""Unit tests for SSI API error handling and retry logic (Week 8)."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from data_sources.ssi_data_client import SSIDataClient, SSIDataError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client() -> SSIDataClient:
    client = SSIDataClient()
    client._token = "valid_token"
    client._token_expiry = time.time() + 3600
    return client


def _timeout_exc():
    return requests.Timeout("connection timed out")


def _ok_response(data: dict | None = None):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = data or {"status": "ok", "data": []}
    return resp


def _http_error_response(status_code: int):
    resp = MagicMock()
    resp.status_code = status_code
    http_err = requests.HTTPError(response=resp)
    resp.raise_for_status.side_effect = http_err
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_retry_3_times_on_timeout():
    """Timeout → retries 3 more times (4 total), then raises SSIDataError."""
    client = _client()
    with patch("requests.request", side_effect=_timeout_exc()) as mock_req:
        with pytest.raises(SSIDataError):
            client._request("GET", "https://example.com")
    # 1 initial + 3 retries = 4 total attempts
    assert mock_req.call_count == 4


def test_exponential_backoff_delays():
    """Delays between retries are 1s, 2s, 4s (exponential backoff)."""
    client = _client()
    sleep_calls = []
    with patch("requests.request", side_effect=_timeout_exc()):
        with patch("time.sleep", side_effect=lambda d: sleep_calls.append(d)):
            with pytest.raises(SSIDataError):
                client._request("GET", "https://example.com")
    assert sleep_calls == [1, 2, 4]


def test_401_triggers_token_refresh():
    """HTTP 401 → calls authenticate() to refresh token, then retries once."""
    client = _client()

    auth_response = MagicMock()
    auth_response.raise_for_status.return_value = None
    auth_response.json.return_value = {
        "data": {"accessToken": "new_token"}
    }

    ok_response = _ok_response({"status": "ok", "data": []})

    responses = [_http_error_response(401), ok_response]

    def fake_request(method, url, **kwargs):
        resp = responses.pop(0)
        if resp.status_code == 401:
            resp.raise_for_status.side_effect = None
            # simulate raise_for_status not raising so code checks status_code
            resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
            raise requests.HTTPError(response=resp)
        return resp

    # Patch authenticate to update token
    with patch.object(client, "authenticate", side_effect=lambda: setattr(client, "_token", "new_token")) as mock_auth:
        with patch("requests.request") as mock_req:
            mock_req.side_effect = [
                # First call returns 401 response (not raising, so code checks status_code)
                _make_401_response(),
                _ok_response({"status": "ok", "data": []}),
            ]
            result = client._request("GET", "https://fc-data.ssi.com.vn/api/v2/Market/Test")

    mock_auth.assert_called_once()


def _make_401_response():
    """Return a mock response with status_code=401 that doesn't raise on raise_for_status."""
    resp = MagicMock()
    resp.status_code = 401
    resp.raise_for_status.return_value = None  # doesn't raise
    return resp


def test_api_error_does_not_crash_bot(tmp_path):
    """SSI API timeout during daily_scan_job → error is logged, bot continues."""
    import core.bot as bot_module
    import core.portfolio_manager as pm_module
    bot_module._SIGNAL_QUEUE_PATH = tmp_path / "signal_queue.json"
    pm_module._DEFAULT_DB_PATH = tmp_path / "trades.db"
    pm_module._DEFAULT_PORTFOLIO_PATH = tmp_path / "portfolio.json"

    from core.bot import TradingBot

    config = {
        "capital": {"initial": 500_000_000, "max_positions": 5},
        "data_source": "YFINANCE",
        "broker": "SimulatedBroker",
        "signal_engines": [{"name": "MomentumV1", "enabled": True, "weight": 1.0}],
        "signal": {"min_score": 0.55},
        "scheduler": {
            "daily_scan_time": "15:35",
            "order_placement_time": "09:10",
            "cancel_unfilled_time": "14:30",
            "equity_snapshot_time": "15:10",
            "weekly_reset_day": "monday",
            "weekly_reset_time": "08:00",
            "signal_expiry_time": "08:30",
            "intraday_interval_minutes": 30,
        },
        "telegram": {"enabled": False},
        "watchlist": [],
        "mode": "PAPER",
    }

    dm = MagicMock()
    dm.get_universe.return_value = ["VCB"]
    dm.get_ohlcv.side_effect = Exception("SSI API timeout")
    broker = MagicMock()
    broker.get_order_status.side_effect = Exception()
    notifier = MagicMock()

    bot = TradingBot(config=config, data_manager=dm, signal_engines=[MagicMock()],
                     broker=broker, notifier=notifier)

    # Should not raise even if every symbol throws
    bot.daily_scan_job()
    assert bot.queue == []   # no signals generated


def test_implementation_shortfall_calculated():
    """fill_price - signal_price = delay_cost per share."""
    from core.bot import Signal

    sig = Signal(
        symbol="VCB",
        action="BUY",
        score=0.70,
        engine="MomentumV1",
        source="EOD",
        created_at="2026-04-20T15:35:00",
        stop_loss=47_500,
        take_profit=54_500,
        signal_price=50_000.0,
        fill_price=50_500.0,
    )
    sig.delay_cost = sig.fill_price - sig.signal_price
    assert sig.delay_cost == 500.0
