from __future__ import annotations

from datetime import date, datetime, timedelta

import pytz

_VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
_MARKET_CLOSE_HOUR = 15
_MARKET_CLOSE_MINUTE = 30


def last_trading_date() -> date:
    """Trả về ngày giao dịch gần nhất đã kết thúc phiên (15:30 VN time).

    - Thứ 2-6, sau 15:30  → hôm nay
    - Thứ 2-6, trước 15:30 → ngày giao dịch trước (lùi qua cuối tuần nếu cần)
    - Thứ 7, CN           → thứ 6 gần nhất
    - Thứ 2, trước 15:30  → thứ 6 tuần trước
    """
    now = datetime.now(_VN_TZ)
    today = now.date()
    market_closed_today = (
        now.hour > _MARKET_CLOSE_HOUR
        or (now.hour == _MARKET_CLOSE_HOUR and now.minute >= _MARKET_CLOSE_MINUTE)
    )

    if today.weekday() < 5 and market_closed_today:
        return today

    # Lùi về ngày trước, bỏ qua cuối tuần
    candidate = today if today.weekday() < 5 else today
    candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:  # 5=Sat, 6=Sun
        candidate -= timedelta(days=1)
    return candidate
