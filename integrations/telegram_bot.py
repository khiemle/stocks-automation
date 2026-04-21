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

    def notify_intraday_report(
        self,
        run_at: str,
        positions: dict,   # {symbol: (Position, price|None)}
        events: dict,
    ) -> bool:
        if not positions:
            return True
        time_str = run_at[11:16] if len(run_at) >= 16 else run_at

        lines = [f"🔄 *Monitor {time_str}*"]

        if events.get("stops_hit"):
            for e in events["stops_hit"]:
                lines.append(f"🛑 Stop hit: {e['symbol']} @ {e['price']:,.0f}  P&L {e['pnl']:+,.0f}")
        if events.get("tps_hit"):
            for e in events["tps_hit"]:
                lines.append(f"🎯 TP hit: {e['symbol']} @ {e['price']:,.0f}  P&L {e['pnl']:+,.0f}")
        if events.get("trails_updated"):
            for e in events["trails_updated"]:
                lines.append(f"🔼 Trail {e['symbol']}: stop {e['old_stop']:,.0f} → {e['new_stop']:,.0f}")
        if events.get("new_signals"):
            lines.append(f"🟢 New signals: {', '.join(events['new_signals'])}")

        has_events = any(events.get(k) for k in ("stops_hit", "tps_hit", "trails_updated", "new_signals"))
        if not has_events:
            lines.append("✅ All clear")

        lines.append("")
        for sym, (pos, price) in positions.items():
            if price and price > 0:
                pnl_pct = (price - pos.avg_price) / pos.avg_price
                arrow = "▲" if pnl_pct >= 0 else "▼"
                lines.append(
                    f"  {sym}  {price:,.0f} {arrow}{pnl_pct:+.1%}"
                    f"  stop {pos.stop_loss:,.0f}"
                )
            else:
                lines.append(f"  {sym}  — (no price)  stop {pos.stop_loss:,.0f}")

        return self.send_message("\n".join(lines))

    def notify_daily_summary(
        self,
        date: str,
        num_trades: int,
        equity: float,
        pnl_pct: float,
        positions: dict | None = None,
        prices: dict | None = None,
        closed_trades: list | None = None,
    ) -> bool:
        direction = "📈" if pnl_pct >= 0 else "📉"
        lines = [
            f"{direction} *Tóm tắt ngày {date}*",
            f"NAV: {equity:,.0f} VND",
            f"P&L ngày: {pnl_pct:+.2%}",
        ]

        if positions:
            lines.append(f"\n📂 *Positions ({len(positions)})*")
            for sym, pos in positions.items():
                price = (prices or {}).get(sym, 0) or 0
                if price > 0:
                    pp = (price - pos.avg_price) / pos.avg_price
                    arrow = "▲" if pp >= 0 else "▼"
                    lines.append(
                        f"  {sym} ×{pos.qty:,}  {price:,.0f} {arrow}{pp:+.1%}"
                        f"  stop {pos.stop_loss:,.0f}"
                    )
                else:
                    lines.append(f"  {sym} ×{pos.qty:,}  entry {pos.avg_price:,.0f}  stop {pos.stop_loss:,.0f}")

        if closed_trades:
            lines.append(f"\n📋 *Đã đóng hôm nay ({len(closed_trades)})*")
            for t in closed_trades:
                tag = "WIN ✅" if t.net_pnl > 0 else "LOSS ❌"
                lines.append(f"  {t.symbol}  {t.net_pnl:+,.0f} VND  {tag}")
        else:
            lines.append("\n📋 Không có giao dịch đóng hôm nay")

        lines.append(f"\n🔔 *Mua mới hôm nay: {num_trades}*")
        return self.send_message("\n".join(lines))
