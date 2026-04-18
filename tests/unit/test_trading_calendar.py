from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

import pytz
import pytest

from core.trading_calendar import last_trading_date

_VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")


def _vn_dt(weekday_iso: int, hour: int, minute: int = 0) -> datetime:
    """Tạo datetime VN timezone cho ngày trong tuần gần nhất có weekday_iso.
    weekday_iso: 1=Mon ... 7=Sun (ISO weekday)
    """
    # Dùng tuần cố định để test ổn định
    # 2026-04-13 = Mon, ..., 2026-04-19 = Sun
    base = date(2026, 4, 13)  # Monday
    d = base + __import__("datetime").timedelta(days=weekday_iso - 1)
    return _VN_TZ.localize(datetime(d.year, d.month, d.day, hour, minute))


def _patch_now(dt: datetime):
    return patch("core.trading_calendar.datetime", wraps=__import__("datetime").datetime,
                 **{"now.return_value": dt})


class TestLastTradingDate:
    def test_weekday_after_close(self):
        """Thứ 4 16:00 → hôm nay (thứ 4)."""
        now = _vn_dt(3, 16, 0)  # Wednesday 16:00
        with patch("core.trading_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = now
            result = last_trading_date()
        assert result == date(2026, 4, 15)  # Wednesday
        assert result.weekday() == 2

    def test_weekday_at_close(self):
        """Thứ 3 15:30 → hôm nay."""
        now = _vn_dt(2, 15, 30)  # Tuesday 15:30
        with patch("core.trading_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = now
            result = last_trading_date()
        assert result == date(2026, 4, 14)  # Tuesday

    def test_weekday_before_close(self):
        """Thứ 4 14:00 → thứ 3."""
        now = _vn_dt(3, 14, 0)  # Wednesday 14:00
        with patch("core.trading_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = now
            result = last_trading_date()
        assert result == date(2026, 4, 14)  # Tuesday
        assert result.weekday() == 1

    def test_saturday(self):
        """Thứ 7 → thứ 6."""
        now = _vn_dt(6, 10, 0)  # Saturday 10:00
        with patch("core.trading_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = now
            result = last_trading_date()
        assert result == date(2026, 4, 17)  # Friday
        assert result.weekday() == 4

    def test_sunday(self):
        """Chủ nhật → thứ 6."""
        now = _vn_dt(7, 20, 0)  # Sunday 20:00
        with patch("core.trading_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = now
            result = last_trading_date()
        assert result == date(2026, 4, 17)  # Friday
        assert result.weekday() == 4

    def test_monday_before_close(self):
        """Thứ 2 09:00 → thứ 6 tuần trước."""
        now = _vn_dt(1, 9, 0)  # Monday 09:00
        with patch("core.trading_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = now
            result = last_trading_date()
        assert result == date(2026, 4, 10)  # Previous Friday
        assert result.weekday() == 4

    def test_monday_after_close(self):
        """Thứ 2 16:00 → hôm nay (thứ 2)."""
        now = _vn_dt(1, 16, 0)  # Monday 16:00
        with patch("core.trading_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = now
            result = last_trading_date()
        assert result == date(2026, 4, 13)  # Monday
        assert result.weekday() == 0

    def test_friday_before_close(self):
        """Thứ 6 10:00 → thứ 5."""
        now = _vn_dt(5, 10, 0)  # Friday 10:00
        with patch("core.trading_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = now
            result = last_trading_date()
        assert result == date(2026, 4, 16)  # Thursday
        assert result.weekday() == 3

    def test_result_is_never_weekend(self):
        """Kết quả không bao giờ là thứ 7 hay CN."""
        for iso_day in range(1, 8):
            for hour in [9, 15, 16]:
                now = _vn_dt(iso_day, hour)
                with patch("core.trading_calendar.datetime") as mock_dt:
                    mock_dt.now.return_value = now
                    result = last_trading_date()
                assert result.weekday() < 5, (
                    f"Got weekend for iso_day={iso_day}, hour={hour}: {result}"
                )
