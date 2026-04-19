from __future__ import annotations

import pandas as pd
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

from core.protocols import SignalResult

_BUY_THRESHOLD = 0.55
_SELL_THRESHOLD = -0.55

_BASE_WEIGHTS: dict[str, float] = {
    "ma": 0.25,
    "macd": 0.25,
    "rsi": 0.20,
    "adx": 0.15,
    "volume": 0.10,
    "foreign": 0.05,
}

_MIN_VOLUME_MA20 = 100_000
_MIN_PRICE = 5_000
_VOL_BREAKOUT_MIN = 1.5  # hard gate: signal bar vol >= 1.5 × vol_MA20 mới BUY


class MomentumV1:
    name = "MomentumV1"
    version = "1.0"

    def evaluate(
        self,
        df: pd.DataFrame,
        foreign_flow: pd.DataFrame | None,
    ) -> SignalResult:
        df = df.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        ema20  = EMAIndicator(close, window=20).ema_indicator()
        ema60  = EMAIndicator(close, window=60).ema_indicator()
        ema200 = EMAIndicator(close, window=200).ema_indicator()
        macd_obj = MACD(close)
        macd_line = macd_obj.macd()
        macd_sig = macd_obj.macd_signal()
        rsi = RSIIndicator(close, window=14).rsi()
        adx_obj = ADXIndicator(high, low, close, window=14)
        adx = adx_obj.adx()
        adx_pos = adx_obj.adx_pos()
        adx_neg = adx_obj.adx_neg()
        atr = AverageTrueRange(high, low, close, window=14).average_true_range()
        vol_ma20 = volume.rolling(20).mean()

        ema20_v  = float(ema20.iloc[-1])
        ema60_v  = float(ema60.iloc[-1])
        ema200_v = float(ema200.iloc[-1]) if not pd.isna(ema200.iloc[-1]) else None
        macd_v = float(macd_line.iloc[-1])
        macd_sig_v = float(macd_sig.iloc[-1])
        rsi_v = float(rsi.iloc[-1])
        adx_v = float(adx.iloc[-1])
        adxp_v = float(adx_pos.iloc[-1])
        adxn_v = float(adx_neg.iloc[-1])
        atr_v = float(atr.iloc[-1])
        close_v = float(close.iloc[-1])
        vol_v = float(volume.iloc[-1])
        vol_ma20_v = float(vol_ma20.iloc[-1]) if not pd.isna(vol_ma20.iloc[-1]) else 0.0

        regime = _detect_regime(adx_v, atr_v, close_v)

        weights = dict(_BASE_WEIGHTS)

        # MA score: % divergence of EMA20 from EMA60, 5% divergence → ±1
        if ema60_v > 0:
            ma_score = _clamp((ema20_v - ema60_v) / ema60_v * 20)
        else:
            ma_score = 0.0

        # MACD score: sign of MACD line (±0.5) + histogram magnitude (±0.5)
        # Histogram scale = 0.03% of close — a 0.03% move is "meaningful" for VN stocks
        if close_v > 0:
            macd_direction = 0.5 if macd_v > 0 else -0.5
            scale = close_v * 0.0003
            hist_component = _clamp((macd_v - macd_sig_v) / scale) * 0.5
            macd_score = _clamp(macd_direction + hist_component)
        else:
            macd_score = 0.0

        # RSI score: 30→-1, 50→0, 70→+1, >75 hard block
        if rsi_v > 75:
            rsi_score = -1.0
        elif rsi_v > 70:
            # linear from +1 at 70 to -1 at 75
            rsi_score = 1.0 - (rsi_v - 70) / 2.5
        else:
            rsi_score = _clamp((rsi_v - 50) / 20)

        # ADX score: directional move scaled by trend strength
        di_total = adxp_v + adxn_v
        if di_total > 0 and adx_v > 0:
            di_diff = (adxp_v - adxn_v) / di_total  # -1 to +1
            strength = min(adx_v / 25.0, 1.0)
            adx_score = _clamp(di_diff * strength)
        else:
            adx_score = 0.0

        # Volume score: ratio vs 20-day average
        if vol_ma20_v > 0:
            vol_score = _clamp(vol_v / vol_ma20_v - 1.0)
        else:
            vol_score = 0.0

        # Foreign flow score
        ff_score = 0.0
        if foreign_flow is not None and not foreign_flow.empty and "net_value" in foreign_flow.columns:
            avg_ff = float(foreign_flow["net_value"].tail(5).mean())
            scale = abs(avg_ff) + 1e-10
            ff_score = _clamp(avg_ff / scale * min(abs(avg_ff) / 1e9, 1.0))
        else:
            weights["foreign"] = 0.0

        # Regime adjustments
        if regime == "VOLATILE":
            confidence_mult = 0.7
        elif regime == "SIDEWAYS":
            weights["ma"] *= 0.7
            confidence_mult = 0.85
        else:
            confidence_mult = 1.0

        # Normalise weights (sum to 1.0)
        total_w = sum(weights.values())
        norm = {k: v / total_w for k, v in weights.items()}

        score = (
            norm["ma"] * ma_score
            + norm["macd"] * macd_score
            + norm["rsi"] * rsi_score
            + norm["adx"] * adx_score
            + norm["volume"] * vol_score
            + norm["foreign"] * ff_score
        )
        score = _clamp(score)

        # RSI > 75 hard gate: never generate BUY
        if rsi_v > 75:
            score = min(score, _BUY_THRESHOLD - 0.01)

        # EMA200 trend filter: only BUY when price is above long-term trend
        # Skipped when EMA200 is unavailable (< 200 bars of history)
        if ema200_v is not None and close_v < ema200_v:
            score = min(score, _BUY_THRESHOLD - 0.01)

        # Volume breakout gate: chặn BUY khi volume bar hiện tại chưa đủ mạnh.
        # Momentum không có volume confirm → dễ chop → stop-out.
        if vol_ma20_v > 0 and vol_v / vol_ma20_v < _VOL_BREAKOUT_MIN:
            score = min(score, _BUY_THRESHOLD - 0.01)

        if score > _BUY_THRESHOLD:
            action = "BUY"
        elif score < _SELL_THRESHOLD:
            action = "SELL"
        else:
            action = "HOLD"

        confidence = _clamp(abs(score) * confidence_mult)

        indicators = {
            "close": close_v,
            "ema20": ema20_v,
            "ema60": ema60_v,
            "ema200": ema200_v,
            "macd": macd_v,
            "macd_signal": macd_sig_v,
            "rsi": rsi_v,
            "adx": adx_v,
            "adx_pos": adxp_v,
            "adx_neg": adxn_v,
            "atr": atr_v,
            "vol_ma20": vol_ma20_v,
            "vol_ratio": vol_v / vol_ma20_v if vol_ma20_v > 0 else None,
        }

        return SignalResult(
            score=score,
            regime=regime,
            action=action,
            indicators=indicators,
            confidence=confidence,
        )

    def evaluate_intraday(
        self,
        df: pd.DataFrame,
        current_price: float,
    ) -> SignalResult:
        df_copy = df.copy()
        df_copy["close"] = df_copy["close"].copy()
        df_copy.iloc[-1, df_copy.columns.get_loc("close")] = current_price
        return self.evaluate(df_copy, foreign_flow=None)

    def is_eligible(
        self,
        df: pd.DataFrame,
        symbol: str,
        portfolio_symbols: list[str],
        t2_lock_symbols: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Return (eligible, reason). Reason is empty string if eligible."""
        vol_ma20 = df["volume"].rolling(20).mean().iloc[-1]
        close = float(df["close"].iloc[-1])

        if pd.isna(vol_ma20) or vol_ma20 < _MIN_VOLUME_MA20:
            return False, f"vol_MA20={vol_ma20:.0f} < {_MIN_VOLUME_MA20}"
        if close < _MIN_PRICE:
            return False, f"price={close:.0f} < {_MIN_PRICE}"
        if symbol in portfolio_symbols:
            return False, "already in portfolio"
        if t2_lock_symbols and symbol in t2_lock_symbols:
            return False, "T+2 lock"
        return True, ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, float(x)))


def _detect_regime(adx: float, atr: float, close: float) -> str:
    if close > 0 and atr / close > 0.03:
        return "VOLATILE"
    if adx > 25:
        return "TRENDING"
    return "SIDEWAYS"
