Phân tích chi tiết tín hiệu giao dịch cho một cổ phiếu từ signal engine MomentumV1.

## Input

User sẽ cung cấp một trong hai dạng:
1. **Tên cổ phiếu** (VD: `VCB`, `HPG`) → đọc từ signal_queue.json
2. **JSON indicators** trực tiếp

## Bước thực hiện

**Bước 1:** Xác định nguồn dữ liệu.
- Nếu input là tên cổ phiếu: đọc `state/signal_queue.json`, tìm signal có `symbol` khớp và status PENDING/APPROVED. Lấy `indicators` từ đó.
- Nếu input là JSON: parse trực tiếp.

**Bước 2:** Tính toán tất cả sub-scores theo đúng logic MomentumV1 (`signals/momentum_v1.py`):

```
WEIGHTS = {ma: 0.25, macd: 0.25, rsi: 0.20, adx: 0.15, volume: 0.10, foreign: 0.05}

Regime:
  - atr/close > 3%  → VOLATILE  (confidence × 0.7)
  - adx > 25        → TRENDING  (confidence × 1.0)
  - else            → SIDEWAYS  (ma_weight × 0.7, confidence × 0.85)
  (foreign_flow = 0 khi không có data → redistribute weight)

MA score    = clamp((ema20 - ema60) / ema60 × 20)
MACD score  = clamp(direction_0.5 + clamp(histogram / (close×0.0003)) × 0.5)
              direction = +0.5 nếu macd > 0, -0.5 nếu macd < 0
RSI score   = clamp((rsi - 50) / 20)   [nếu rsi ≤ 70]
              linear 1→-1 khi rsi 70→75 [nếu 70 < rsi ≤ 75]
              -1.0 nếu rsi > 75
ADX score   = clamp((adx_pos - adx_neg)/(adx_pos + adx_neg) × min(adx/25, 1))
Volume score= clamp(vol_ratio - 1.0)
clamp(x)    = max(-1.0, min(1.0, x))

Hard gates (nếu vi phạm → score capped tại 0.54, không ra BUY):
  - close < ema200
  - vol_ratio < 1.5
  - rsi > 75
  - macro bearish (nếu có market_context)
```

**Bước 3:** Xuất phân tích theo format sau:

---

### 📊 Phân tích tín hiệu: {SYMBOL}

**Regime:** {TRENDING/SIDEWAYS/VOLATILE} | **Score:** {score} | **Action:** {BUY/HOLD}

#### Bức tranh giá

Vẽ ASCII chart so sánh close với các đường EMA:
```
{close}  ◄── close
────────────────────
{ema20}  ── EMA20
{ema60}  ── EMA60
{ema200} ── EMA200   ← [close trên/dưới EMA200]
```
Diễn giải bằng tiếng Việt: giá đang ở đâu so với xu hướng ngắn/trung/dài hạn.

#### Sub-scores chi tiết

Với từng chỉ số, hiển thị:
- **Công thức tính** với số thực
- **Visual bar** (ví dụ: `████░░ +0.64`)
- **Diễn giải**: ý nghĩa thực tế của con số này là gì

| Chỉ số | Sub-score | Trọng số | Đóng góp | Nhận xét ngắn |
|--------|-----------|----------|----------|---------------|
| MA (EMA20 vs EMA60) | ... | ...% | ... | ... |
| MACD | ... | ...% | ... | ... |
| RSI | ... | ...% | ... | ... |
| ADX | ... | ...% | ... | ... |
| Volume | ... | ...% | ... | ... |
| **TỔNG** | | | **{score}** | |

#### Gates kiểm tra

```
✅/❌ EMA200 filter: close {so sánh} ema200
✅/❌ Volume gate:   vol_ratio {x} ≥ 1.5×
✅/❌ RSI gate:      rsi {x} < 75
```

#### Risk / Reward

```
Entry (ATO ước tính): {close}
Stop Loss:  {stop_loss}  ({pct_stop}% = 1.5 × ATR {atr})
Take Profit:{take_profit} ({pct_tp}%  = 4.5 × ATR)
R:R ratio = 1 : {ratio}
```

#### Điểm mạnh / Điểm yếu

**Mạnh:** (liệt kê các chỉ số đang tích cực)
**Yếu:** (liệt kê cảnh báo)
**Khuyến nghị:** APPROVE nếu... / CẨN THẬN nếu... / REJECT nếu...

---

## Lưu ý khi phân tích

- Luôn tính toán số thực, không ước lượng
- Nếu signal có `stop_loss` và `take_profit` trong JSON → dùng luôn, không tính lại
- Regime SIDEWAYS → nhắc rằng MA weight đã giảm 30%
- Score sát ngưỡng 0.55–0.65 → nhấn mạnh đây là tín hiệu yếu, cần thêm xác nhận
- Score ≥ 0.80 → tín hiệu mạnh, nhưng vẫn phải check gates
