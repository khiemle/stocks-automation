# Paper Trading Runbook

Hướng dẫn vận hành hàng ngày cho VN Auto Trading System — Phase 1 (Paper Trading).

---

## 1. Tổng quan lịch chạy

| Thời gian | Job | Mô tả |
|---|---|---|
| 08:30 | signal_expiry | Expire các PENDING signal từ hôm trước |
| 09:10 | order_placement | Đặt lệnh ATO cho các signal đã APPROVE |
| 14:30 | cancel_unfilled | Hủy lệnh ORDER_PLACED chưa khớp |
| 15:10 | equity_snapshot | Ghi NAV vào DB |
| 15:35 | daily_scan | Quét toàn bộ universe, tạo PENDING signals |
| 16:00 | daily_summary | Telegram: tóm tắt ngày |
| Mỗi 30 phút (09:00–15:30) | intraday_monitor | Kiểm tra stop loss / trailing stop |
| Thứ 2 08:00 | weekly_reset | Reset baseline P&L tuần |

---

## 2. Khởi động hệ thống

### Lần đầu (setup)

```bash
# 1. Cài dependencies
pip install -r requirements.txt

# 2. Tải dữ liệu lịch sử (5 năm, ~5–10 phút)
python trading_bot.py init-data --years 5

# 3. Kiểm tra data
python trading_bot.py validate

# 4. Chạy thử scan
python trading_bot.py scan
```

### Mỗi ngày trước 09:00

```bash
# Update data lên ngày hôm nay
python trading_bot.py update-daily

# Khởi động bot (chạy nền)
nohup python trading_bot.py start > /dev/null 2>&1 &
echo $! > .bot.pid
echo "Bot started, PID: $(cat .bot.pid)"
```

### Khởi động dashboard (terminal riêng)

```bash
streamlit run streamlit_app.py
# Mở browser: http://localhost:8501
```

---

## 3. Quy trình hàng ngày

### 15:35 — Nhận signal qua Telegram

Bot scan xong → Telegram gửi tin BUY signals. Mỗi tin có:
- Symbol, score, giá đóng cửa
- Link dashboard để xem chi tiết

### 15:35–08:30 hôm sau — Review và quyết định

Vào **Streamlit → Trang 2 (Signals)**:

| Hành động | Khi nào |
|---|---|
| **APPROVE** | Score ≥ 0.60, regime TRENDING, không có news xấu |
| **REJECT** | Nghi ngờ, đã có quá nhiều position, hoặc muốn bỏ qua |
| Không làm gì | Signal tự EXPIRE lúc 08:30 hôm sau |

**Tiêu chí APPROVE nhanh:**
- Score ≥ 0.60
- Regime: TRENDING hoặc SIDEWAYS (không phải VOLATILE)
- RSI 40–65 (không overbought)
- ADX ≥ 20 (có xu hướng)
- Vol/MA20 ≥ 1.0 (có khối lượng)
- Không quá 5 positions đang mở

### 09:10 — Xác nhận lệnh đã đặt

Kiểm tra Telegram: thông báo "Lệnh khớp" cho các APPROVED signals.
Vào **Streamlit → Trang 1 (Dashboard)** kiểm tra positions mới.

---

## 4. Giám sát intraday (09:00–15:30)

Bot tự động kiểm tra mỗi 30 phút. Telegram thông báo ngay khi:
- Stop loss bị chạm → lệnh SELL đã đặt
- Take profit bị chạm → lệnh SELL đã đặt

Không cần làm gì thêm. Nếu muốn thoát thủ công:
→ Vào **Streamlit → Trang 1**, tìm position → (Phase 1: chỉnh stop loss xuống giá hiện tại để trigger tự động)

---

## 5. Dừng và khởi động lại bot

```bash
# Dừng bot
kill $(cat .bot.pid) && rm .bot.pid
echo "Bot stopped"

# Khởi động lại (portfolio và signal queue được load lại tự động)
python trading_bot.py start &
```

Bot khởi động lại sẽ tự động:
1. Load lại `data/portfolio.json`
2. Load lại `state/signal_queue.json`
3. Kiểm tra trạng thái các ORDER_PLACED signal

---

## 6. Monitoring hàng tuần

```bash
# Xem log lỗi
tail -50 logs/errors.log

# Xem scan log
tail -20 logs/scan.log

# Backtest nhanh để so sánh với paper trading
python trading_bot.py backtest VCB --years 1
python trading_bot.py backtest-all
```

Vào **Streamlit → Trang 4 (Reports)**:
- Kiểm tra Sharpe Ratio, Win Rate, MDD
- Export CSV trade log để review

---

## 7. Circuit Breaker

Nếu MDD thực tế vượt **150% MDD backtest** (~30%), Telegram gửi cảnh báo `CIRCUIT BREAKER`.

**Khi nhận cảnh báo:**
1. Dừng bot ngay: `kill $(cat .bot.pid)`
2. Vào Streamlit → Trang 3, tắt bot
3. Review toàn bộ trade log
4. Xác định nguyên nhân (strategy failure? data issue? market regime change?)
5. Chỉ khởi động lại sau khi hiểu rõ nguyên nhân

---

## 8. Xử lý sự cố thường gặp

### Bot không scan được symbol

```bash
# Kiểm tra data
python trading_bot.py validate --symbol VCB

# Update lại data cho symbol đó
python trading_bot.py update-daily
```

### Signal queue bị corrupt

```bash
# Backup và reset
cp state/signal_queue.json state/signal_queue.backup.json
echo "[]" > state/signal_queue.json
```

### Data lỗi / thiếu ngày

```bash
# Re-download toàn bộ (mất 5–10 phút)
python trading_bot.py init-data --years 3
```

### Bot crash giữa chừng

```bash
# Kiểm tra log
tail -50 logs/bot.log | grep ERROR

# Khởi động lại bình thường — state tự phục hồi
python trading_bot.py start &
```

### Telegram không nhận tin

```bash
# Test nhanh
python -c "
import json
from integrations.telegram_bot import TelegramNotifier
config = json.load(open('config/config.json'))
print(TelegramNotifier.from_config(config).send_message('test'))
"
```

---

## 9. Milestone Phase 1

Paper trading đạt chuẩn khi sau **60 ngày**:

| Metric | Target |
|---|---|
| Sharpe Ratio | ≥ 1.0 |
| Max Drawdown | ≤ 15% |
| Win Rate | ≥ 52% |
| Số giao dịch | ≥ 30 |
| Bug nghiêm trọng | 0 |

Theo dõi progress: **Streamlit → Trang 4** mỗi tuần.

---

## 10. Checklists

### Checklist khởi động ngày

- [ ] `python trading_bot.py update-daily` đã chạy xong
- [ ] Bot process đang chạy (`ps aux | grep trading_bot`)
- [ ] Streamlit accessible tại localhost:8501
- [ ] `logs/errors.log` không có lỗi mới từ hôm qua
- [ ] Telegram bot còn hoạt động (gửi test message nếu nghi ngờ)

### Checklist cuối tuần

- [ ] Export trade log CSV từ Streamlit
- [ ] Tính Sharpe, Win Rate, MDD thực tế
- [ ] So sánh với backtest metrics
- [ ] Review các lệnh REJECT: có bỏ lỡ cơ hội nào không?
- [ ] Check `logs/errors.log` cho cả tuần
- [ ] Update data: `python trading_bot.py update-daily`
