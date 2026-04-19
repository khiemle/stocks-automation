from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Send trade notifications via Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._enabled = enabled

    @classmethod
    def from_config(cls, config: dict) -> "TelegramNotifier":
        tg = config.get("telegram", {})
        return cls(
            bot_token=tg.get("bot_token", ""),
            chat_id=tg.get("chat_id", ""),
            enabled=tg.get("enabled", False),
        )

    def send_message(self, text: str) -> bool:
        if not self._enabled:
            return True
        try:
            url = _TELEGRAM_API.format(token=self._token)
            resp = requests.post(
                url,
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("Telegram send failed: %s", exc)
            return False

    def notify_buy_signal(
        self,
        symbol: str,
        score: float,
        price: float,
        web_url: str = "",
    ) -> bool:
        link = f"\n[Xem dashboard]({web_url})" if web_url else ""
        text = (
            f"\U0001f7e2 *BUY Signal: {symbol}*\n"
            f"Score: {score:+.3f}\n"
            f"Giá: {price:,.0f} VND"
            f"{link}"
        )
        return self.send_message(text)

    def notify_order_filled(
        self, symbol: str, fill_price: float, qty: int, side: str
    ) -> bool:
        emoji = "\u2705" if side == "B" else "\U0001f534"
        side_str = "MUA" if side == "B" else "BÁN"
        text = (
            f"{emoji} *Lệnh khớp: {symbol}*\n"
            f"Hành động: {side_str}\n"
            f"Số lượng: {qty:,}\n"
            f"Giá khớp: {fill_price:,.0f} VND"
        )
        return self.send_message(text)

    def notify_stop_loss_hit(
        self, symbol: str, exit_price: float, pnl: float
    ) -> bool:
        text = (
            f"\U0001f6d1 *Stop Loss: {symbol}*\n"
            f"Giá thoát: {exit_price:,.0f} VND\n"
            f"P&L: {pnl:+,.0f} VND"
        )
        return self.send_message(text)

    def notify_tp_hit(self, symbol: str, exit_price: float, pnl: float) -> bool:
        text = (
            f"\U0001f3af *Take Profit: {symbol}*\n"
            f"Giá thoát: {exit_price:,.0f} VND\n"
            f"P&L: {pnl:+,.0f} VND"
        )
        return self.send_message(text)

    def notify_circuit_breaker(
        self, mdd_pct: float, threshold_pct: float
    ) -> bool:
        text = (
            f"\U0001f6a8 *CIRCUIT BREAKER KÍCH HOẠT*\n"
            f"MDD hiện tại: {mdd_pct:.1%}\n"
            f"Ngưỡng: {threshold_pct:.1%}\n"
            f"Trạng thái: *STOPPED* — Không đặt lệnh mới"
        )
        return self.send_message(text)

    def notify_daily_summary(
        self,
        date: str,
        num_trades: int,
        equity: float,
        pnl_pct: float,
    ) -> bool:
        direction = "\U0001f4c8" if pnl_pct >= 0 else "\U0001f4c9"
        text = (
            f"{direction} *Tóm tắt ngày {date}*\n"
            f"Số giao dịch: {num_trades}\n"
            f"NAV: {equity:,.0f} VND\n"
            f"P&L ngày: {pnl_pct:+.2%}"
        )
        return self.send_message(text)
