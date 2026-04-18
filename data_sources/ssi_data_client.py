from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import List

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://fc-data.ssi.com.vn/api/v2/Market"
_AUTH_URL = "https://fc-data.ssi.com.vn/api/v2/Market/AccessToken"
_RETRY_DELAYS = (1, 2, 4)   # exponential backoff seconds


class SSIAuthError(Exception):
    pass


class SSIDataError(Exception):
    pass


class SSIDataClient:
    name = "SSI"

    def __init__(self) -> None:
        self._consumer_id = os.environ.get("SSI_CONSUMER_ID", "")
        self._consumer_secret = os.environ.get("SSI_CONSUMER_SECRET", "")
        self._token: str | None = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def authenticate(self) -> str:
        resp = self._post(
            _AUTH_URL,
            json={"consumerID": self._consumer_id, "consumerSecret": self._consumer_secret},
            auth=False,
        )
        data = resp.get("data", {})
        token = data.get("accessToken")
        if not token:
            raise SSIAuthError(f"Authentication failed: {resp}")
        self._token = token
        # SSI tokens typically expire in 24h; we refresh after 23h
        self._token_expiry = time.time() + 23 * 3600
        return token

    def _ensure_token(self) -> str:
        if not self._token or time.time() >= self._token_expiry:
            self.authenticate()
        return self._token  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Daily OHLCV
    # ------------------------------------------------------------------

    def get_daily_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        rows = []
        page = 1
        while True:
            resp = self._get(
                f"{_BASE_URL}/DailyOhlc",
                params={
                    "symbol": symbol,
                    "fromDate": start,
                    "toDate": end,
                    "pageIndex": page,
                    "pageSize": 100,
                    "ascending": "true",
                },
            )
            data = resp.get("data", [])
            if not data:
                break
            rows.extend(data)
            if len(data) < 100:
                break
            page += 1
        return self._to_ohlcv_df(rows)

    def get_daily_ohlcv_batch(
        self, symbols: List[str], start: str, end: str
    ) -> dict[str, pd.DataFrame]:
        result: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            try:
                result[symbol] = self.get_daily_ohlcv(symbol, start, end)
            except Exception as exc:
                logger.warning("SSI batch failed for %s: %s", symbol, exc)
        return result

    # ------------------------------------------------------------------
    # Intraday
    # ------------------------------------------------------------------

    def get_intraday_price(self, symbol: str) -> float | None:
        try:
            resp = self._get(
                f"{_BASE_URL}/IntradayOhlc",
                params={"symbol": symbol, "pageIndex": 1, "pageSize": 1, "ascending": "false"},
            )
            data = resp.get("data", [])
            if data:
                return float(data[0].get("close", 0)) or None
        except Exception as exc:
            logger.warning("SSI intraday price failed for %s: %s", symbol, exc)
        return None

    def get_intraday_prices_batch(
        self, symbols: List[str]
    ) -> dict[str, float | None]:
        return {s: self.get_intraday_price(s) for s in symbols}

    # ------------------------------------------------------------------
    # Universe
    # ------------------------------------------------------------------

    def get_universe(self, exchange: str) -> List[str]:
        symbols: List[str] = []
        page = 1
        while True:
            resp = self._get(
                f"{_BASE_URL}/Securities",
                params={"exchange": exchange, "pageIndex": page, "pageSize": 500},
            )
            data = resp.get("data", [])
            if not data:
                break
            for item in data:
                code = item.get("symbol") or item.get("code")
                if code:
                    symbols.append(code)
            if len(data) < 500:
                break
            page += 1
        return symbols

    # ------------------------------------------------------------------
    # Foreign flow
    # ------------------------------------------------------------------

    def get_foreign_flow(
        self, symbol: str, start: str, end: str
    ) -> pd.DataFrame | None:
        try:
            resp = self._get(
                f"{_BASE_URL}/ForeignRoom",
                params={"symbol": symbol, "fromDate": start, "toDate": end},
            )
            data = resp.get("data", [])
            if not data:
                return None
            df = pd.DataFrame(data)
            df["date"] = pd.to_datetime(df["tradingDate"])
            df = df.rename(columns={
                "buyVolume": "buy_volume",
                "sellVolume": "sell_volume",
                "netValue": "net_value",
            })
            return df.set_index("date")[["buy_volume", "sell_volume", "net_value"]].sort_index()
        except Exception as exc:
            logger.warning("SSI foreign flow failed for %s: %s", symbol, exc)
            return None

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> dict:
        return self._request("GET", url, params=params)

    def _post(self, url: str, json: dict | None = None, auth: bool = True) -> dict:
        return self._request("POST", url, json=json, auth=auth)

    def _request(
        self, method: str, url: str, auth: bool = True, **kwargs
    ) -> dict:
        headers = {}
        if auth:
            headers["Authorization"] = f"Bearer {self._ensure_token()}"

        last_exc: Exception = RuntimeError("No attempts made")
        for attempt, delay in enumerate((*_RETRY_DELAYS, None), start=1):
            try:
                resp = requests.request(
                    method, url, headers=headers, timeout=10, **kwargs
                )
                if resp.status_code == 401 and auth:
                    # Token expired mid-session — refresh once and retry
                    logger.info("SSI 401 — refreshing token")
                    self.authenticate()
                    headers["Authorization"] = f"Bearer {self._token}"
                    resp = requests.request(
                        method, url, headers=headers, timeout=10, **kwargs
                    )
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_exc = exc
                if delay is not None:
                    logger.warning(
                        "SSI request failed (attempt %d/%d): %s — retrying in %ds",
                        attempt, len(_RETRY_DELAYS) + 1, exc, delay,
                    )
                    time.sleep(delay)

        raise SSIDataError(f"SSI API failed after {len(_RETRY_DELAYS)+1} attempts: {last_exc}") from last_exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_ohlcv_df(rows: list) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df.get("tradingDate", df.get("date")))
        df = df.rename(columns={
            "openPrice": "open",
            "highPrice": "high",
            "lowPrice": "low",
            "closePrice": "close",
            "totalVolume": "volume",
        })
        df = df.set_index("date")
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df[["open", "high", "low", "close", "volume"]].sort_index()
