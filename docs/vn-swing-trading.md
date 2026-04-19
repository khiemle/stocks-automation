# VN Swing Trading — Nguồn Chính Thống Về Thuật Toán

> **Đây là tài liệu trung tâm về thuật toán đang áp dụng cho hệ thống.**
> Mọi thay đổi về signal, risk, execution, hoặc backtest methodology PHẢI cập nhật file này cùng lúc với code theo [Commit Protocol](#5-commit-protocol) ở cuối file.
>
> **Cập nhật lần cuối**: 2026-04-19 · **Commit**: `d71eff7` · **Phiên bản baseline**: `MomentumV1 v1.0`

---

## Mục lục

1. [Thuật toán hiện tại](#1-thuật-toán-hiện-tại)
2. [Hiệu suất baseline (VN30 5 năm)](#2-hiệu-suất-baseline)
3. [Roadmap cải tiến](#3-roadmap-cải-tiến)
4. [Change Log](#4-change-log)
5. [Commit Protocol](#5-commit-protocol)

---

## 1. Thuật toán hiện tại

### 1.1 Signal Engine — `MomentumV1 v1.0`

File: `signals/momentum_v1.py`

#### Scoring (tổng trọng số base = 1.0)

| Thành phần | Trọng số | Công thức | Range |
|------------|---------:|-----------|:-----:|
| MA divergence | 0.25 | `clamp((ema20 - ema60) / ema60 × 20)` | [-1, +1] |
| MACD | 0.25 | `sign(macd)×0.5 + clamp(hist / (close × 0.0003))×0.5` | [-1, +1] |
| RSI14 | 0.20 | `(rsi - 50) / 20` · giảm dần từ +1 ở mức 70 xuống -1 ở mức 75 | [-1, +1] |
| ADX14 | 0.15 | `(DI+ - DI-)/(DI+ + DI-) × min(adx/25, 1)` | [-1, +1] |
| Volume | 0.10 | `vol / vol_MA20 - 1` | [-1, +1] |
| Foreign flow | 0.05 | `avg5(net_value)` scaled · trọng số → 0 nếu thiếu dữ liệu | [-1, +1] |

Composite score = tổng có trọng số, chuẩn hoá sau khi điều chỉnh regime.

#### Phát hiện Regime

| Regime | Điều kiện | Tác động |
|--------|-----------|----------|
| VOLATILE | `ATR/close > 3%` | confidence × 0.7 |
| SIDEWAYS | `ADX ≤ 25` (và không VOLATILE) | MA weight × 0.7, confidence × 0.85 |
| TRENDING | `ADX > 25` (và không VOLATILE) | không điều chỉnh |

#### Hard Gates (chặn BUY)

- `RSI14 > 75` → score bị clamp về `_BUY_THRESHOLD - 0.01`
- `close < EMA200` → score bị clamp về `_BUY_THRESHOLD - 0.01` *(trend filter — bỏ qua nếu có < 200 bars lịch sử)*

#### Ngưỡng quyết định

| Hành động | Điều kiện |
|-----------|-----------|
| BUY | score > `+0.55` |
| SELL | score < `-0.55` |
| HOLD | còn lại |

#### Điều kiện đủ (`MomentumV1.is_eligible`)

- `vol_MA20 ≥ 100,000` cổ phiếu
- `close ≥ 5,000` VND
- symbol không nằm trong portfolio hiện tại
- symbol không nằm trong danh sách khoá T+2

### 1.2 Risk Engine

File: `core/risk_engine.py`

| Tham số | Giá trị | Cách dùng |
|---------|--------:|-----------|
| `ATR_STOP_MULT` | 1.5 | `stop = entry − 1.5 × ATR14` |
| `ATR_TP_MULT` | 4.5 | `TP = entry + 4.5 × ATR14` (R:R ≈ 1:3) |
| `RISK_PCT` | 2% | rủi ro per-trade so với cash hiện tại |
| `MAX_POSITION_PCT` | 20% | giới hạn half-Kelly mỗi vị thế |
| `MAX_ADV_PCT` | 5% | max order size so với 20-day ADV |
| Weekly warn | -1.5% | soft limit — cảnh báo |
| Weekly stop | -3.0% | hard limit — tạm dừng BUY mới |
| MDD circuit breaker | 150% × backtest MDD | latch STOP ALL |
| HOSE price band | ±7% | stop phải nằm trong biên độ |
| HNX price band | ±10% | stop phải nằm trong biên độ |

Position sizing: `shares = min(risk_budget / stop_dist, position_cap / close, adv_cap)`, sau đó làm tròn xuống theo lot VN (100 cổ phiếu).

### 1.3 Execution — `SimulatedBroker` (Phase 1)

File: `brokers/simulated_broker.py` · **Source of truth cho `_COMMISSION_RATE` và `_SLIPPAGE_RATE`.**

| Tham số | Giá trị |
|---------|--------:|
| Commission | 0.15% mỗi chiều |
| Slippage | 0.10% mỗi chiều |
| Thời điểm fill | giá open T+1 |
| Settlement | T+2 enforced qua `pd.bdate_range` (≥ 2 ngày làm việc buy→sell) |

### 1.4 Backtester Methodology

File: `core/backtester.py`

- **Warmup**: `_WARMUP_BARS = 252` — không generate signal cho đến bar 252 để EMA200 được calibrate trên lịch sử trước cửa sổ test.
- **Load dữ liệu**: `_load(symbol, years)` trả về `df.tail(years × 365 + 252)` bars.
- **Walk-forward**: chia 70/30 in-sample/out-of-sample. OOS slice prepend thêm `_WARMUP_BARS` bars từ cuối IS để giữ EMA200 calibrated trong OOS.
- **Luồng xử lý mỗi bar T**:
  1. Tại close(T) → đánh giá signal trên `df[:T+1]` (không look-ahead)
  2. Pending BUY/SELL fill tại open(T+1) qua `SimulatedBroker.process_next_bar`
  3. Stop/TP kiểm tra trên high/low từ T+1 trở đi, nhưng chỉ khi đã qua T+2 từ entry
  4. Chặn re-entry trên bar bị stop-out (không BUY ngay sau forced exit)
- **Benchmark**: buy-hold return per-symbol (mua ở close của warmup bar, bán tại close cuối cùng, tính đủ round-trip costs). VN-Index không có sẵn trên yfinance.

---

## 2. Hiệu suất baseline

**Cửa sổ**: 2021-04-19 → 2026-04-17 (5 năm, đi qua crash 2022 + hồi phục 2023-2025)
**Universe**: VN30 (31 symbols — thừa 1 vs danh sách chuẩn 30)
**Dữ liệu**: `data/backtest_vn30_2021-2026.csv`
**Phiên bản algo**: `MomentumV1 v1.0` (EMA200 filter bật)

### 2.1 Aggregate Metrics

| Metric | Giá trị | Mục tiêu | Status |
|--------|--------:|---------:|:------:|
| Median total return | +0.15% | > 75% (5yr ≈ 15%/năm) | ❌ |
| Mean total return | +1.79% | > 75% | ❌ |
| Median Sharpe | 0.025 | > 1.0 | ❌ |
| Median MDD | 5.24% | < 15% | ✅ |
| Median win rate | 33.33% | > 52% | ❌ |
| Median profit factor | 0.98 | > 1.5 | ❌ |
| Median alpha vs B&H | -33.00% | > 0 | ❌ |
| Symbols có +alpha | 7 / 31 | > 15 / 31 | ❌ |
| Tổng trades | 478 | ≥ 300 | ✅ |

### 2.2 Điểm sáng/tối per-symbol

**Alpha tốt nhất** (chiến lược tạo thêm giá trị):
| Symbol | Strategy | B&H | Alpha |
|--------|---------:|----:|------:|
| PDR | +2.97% | -73.62% | **+76.59%** |
| SAB | -10.37% | -35.52% | +25.15% |
| BCM | +0.04% | -21.70% | +21.73% |
| TPB | +2.34% | -10.27% | +12.60% |
| SSI | +12.30% | +0.57% | +11.73% |

**Alpha tệ nhất** (chiến lược bỏ lỡ lợi nhuận):
| Symbol | Strategy | B&H | Alpha |
|--------|---------:|----:|------:|
| VIC | +19.86% | +383.16% | **-363.30%** |
| VHM | +12.61% | +269.25% | -256.64% |
| HDB | -4.37% | +147.83% | -152.20% |
| STB | +10.27% | +120.19% | -109.92% |
| MBB | -0.90% | +92.80% | -93.71% |

### 2.3 Quan sát chính

1. **EMA200 filter hoạt động như hàng phòng ngự** — 5/7 symbols có alpha dương đều có B&H âm (PDR, SAB, BCM, TPB, PLX). Filter thành công trong việc tránh cổ phiếu downtrend.
2. **Chiến lược không giữ được winner** — VIC tăng 383% nhưng chiến lược chỉ bắt được 19.86%. R:R 1:3 với TP cố định gây exit sớm trên uptrend mạnh.
3. **Win rate 33% với R:R 1:3** cho EV hoà vốn nhưng không có biên an toàn — cần hoặc tăng +5-7pp win rate hoặc exit bất đối xứng.
4. **Tần suất trade thấp** (~15 trades/symbol/5yr = 3/năm) — BUY_THRESHOLD 0.55 + EMA200 gate quá khắt khe. Trades tập trung vào vài symbols.
5. **Đồng nhất giữa các symbols**: Sharpe gần 0, MDD đều < 15% — hệ low-activity, low-drawdown, low-return.

---

## 3. Roadmap cải tiến

Status: `[ ]` todo · `[~]` đang làm · `[x]` xong (kèm commit SHA + impact đo được)

### 3.1 Market-Level Filters

- [ ] **VN30 macro regime filter** — tính basket VN30 equal-weight và EMA50; chặn BUY mới khi basket < basket EMA50
  - **Rationale**: 70% tương quan giữa cổ phiếu VN30 và basket. Đi ngược macro = lỗ nặng trong bear market (2022).
  - **Impact dự kiến**: giảm false BUY trong bear period; cải thiện MDD và win rate.
  - **Success**: MDD ≤ 4%, win rate ≥ 38%
- [ ] **Relative strength vs VN30 basket** — chỉ BUY khi return(20d) của symbol > return(20d) của basket
  - **Rationale**: Swing momentum cần leadership so với thị trường. Run như VIC/VHM đến từ stock dẫn dắt basket.
  - **Impact dự kiến**: tập trung vào leader, tránh laggard.
  - **Success**: median alpha > -15% (vs hiện tại -33%)

### 3.2 Entry Refinement

- [ ] **Xác nhận volume breakout** — yêu cầu `vol > 150% × vol_MA20` trên signal bar
  - **Rationale**: weight 0.10 hiện tại cho phép BUY trên volume yếu. Momentum không có volume = chop.
  - **Success**: win rate ≥ 40%
- [ ] **Yêu cầu MACD zero-line** — thêm hard gate: MACD line phải > 0 mới BUY (không chỉ > signal)
  - **Rationale**: gate hiện tại cho phép BUY khi cả MACD & signal đều âm (vẫn downtrend).
  - **Success**: win rate ≥ 36%
- [ ] **Tránh BUY cuối phiên** (chỉ live scan) — scan lúc 15:35, nhưng tag signal > 14:45 là "late" và yêu cầu score > 0.65 thay vì 0.55
  - **Rationale**: Late-session rally hay gap down sáng hôm sau.
  - **Success**: Avg gap loss giảm
- [ ] **Bỏ EMA200 cho small-cap** — filter quá strict cho recovery play; skip filter khi symbol ở recovery regime (price > 52w low × 1.3)

### 3.3 Exit Refinement (impact lớn nhất)

- [ ] **Trailing stop sau +1R** — khi unrealized gain > 1R (= 1.5×ATR), trail stop tại `high - 2×ATR`; bỏ TP cố định
  - **Rationale**: case VIC — algo exit tại +4.5R, bỏ lỡ 40R sau đó. Trailing cho phép winner chạy.
  - **Impact dự kiến**: Rất lớn (đòn bẩy lớn nhất trong backtest).
  - **Success**: Profit factor ≥ 1.5, avg win ≥ 2× hiện tại
- [ ] **TP thích nghi theo regime** — TRENDING: giữ ATR×4.5 hoặc trailing; SIDEWAYS: giảm còn ATR×2; VOLATILE: giảm còn ATR×1.5
  - **Rationale**: Sideways cho lại profit nhanh — chốt sớm.
  - **Success**: win rate trong SIDEWAYS ≥ 45%
- [ ] **Breakeven stop sau +1R** — kéo stop về entry khi đạt +1R (bảo vệ chống lỗ)
  - **Rationale**: thay đổi nhỏ, ngăn winning-to-loss.
  - **Success**: Avg loss giảm 20%

### 3.4 Position Sizing

- [ ] **Kelly fraction từ 30-trade rolling** — sau 30 trades, dùng `half-Kelly = 0.5 × (W - (1-W)/R)` giới hạn ở 2%
  - **Rationale**: 2% cố định hiện tại không thích nghi với edge quan sát được.
  - **Success**: CAGR +2% mà MDD không tăng > +2%
- [ ] **Risk điều chỉnh theo volatility** — regime VOLATILE: giảm `RISK_PCT` xuống 1% (từ 2%)
  - **Rationale**: Volatile = stop dễ bị hit; giảm size bảo vệ vốn.
  - **Success**: MDD trong period VOLATILE giảm ≥ 3pp

### 3.5 Portfolio-Level

- [ ] **Giới hạn concentration theo sector** — tối đa 2 vị thế mở cùng sector (ngân hàng, BĐS, thép, bán lẻ)
  - **Rationale**: VN30 có 6-7 ngân hàng + 4-5 BĐS. Tương quan nội ngành cao.
  - **Success**: Sharpe điều chỉnh correlation ≥ 0.5
- [ ] **Lọc vị thế theo correlation** — từ chối BUY mới nếu `corr(20d, existing_positions) > 0.7`
  - **Rationale**: Phiên bản thống kê của sector filter.
  - **Success**: equity curve mượt hơn

### 3.6 Signal Engine Extensions (Phase 2+)

- [ ] **Foreign flow từ SSI** — khi Phase 2 có SSI integration, tăng foreign-flow weight từ 0.05 → 0.15
  - **Rationale**: Foreign flow là leading indicator mạnh ở VN; 0.05 quá thấp.
  - **Success**: win rate ≥ 45%
- [ ] **Intraday volume profile** — giữa phiên (≥ 10:30) check cumulative vol > 50% projected daily vol trước khi vào lệnh
  - **Rationale**: Xác nhận momentum sớm hơn trong phiên.

### 3.7 Validation Mô Hình

- [ ] **Stress test crash 2022** — backtest riêng cửa sổ Q2-Q3 2022
  - **Success**: MDD trong period đó < 10% (vs ~15% buy-hold)
- [ ] **Parameter sensitivity grid** — sweep BUY_THRESHOLD ∈ {0.45, 0.50, 0.55, 0.60, 0.65} × ATR_TP_MULT ∈ {2, 3, 4.5, 6, trailing}
  - **Success**: xác định flat plateau (robust) vs sharp peak (overfit)
- [ ] **Walk-forward re-validation** — sau khi implement Top-3 cải tiến, chạy lại `run_all(walk_forward=True)`
  - **Success**: IS/OOS Sharpe lệch < 0.3

### 3.8 Thứ tự ưu tiên (đề xuất)

Dựa trên **impact dự kiến × độ dễ implement**:

1. 🔥 **Trailing stop** (3.3) — đòn bẩy lớn nhất; case VIC/VHM cho thấy cơ hội gấp 10x
2. 🔥 **Relative strength vs VN30 basket** (3.1) — dồn vốn vào leader
3. 🔥 **TP thích nghi theo regime** (3.3) — dễ implement, rationale rõ
4. **VN30 macro filter** (3.1) — cải thiện phòng ngự
5. **Xác nhận volume breakout** (3.2) — lọc chất lượng
6. **Giới hạn concentration sector** (3.5) — giảm correlation ẩn

---

## 4. Change Log

| Ngày | Thay đổi | Commit | Ghi chú |
|------|----------|--------|---------|
| 2026-04-19 | **SSoT doc + baseline VN30 5 năm** | `d71eff7` | 31 symbols, median alpha -33% |
| 2026-04-19 | Thêm buy-hold benchmark + alpha vào metrics | `24b6cd2` | BacktestMetrics.benchmark_return, alpha |
| 2026-04-19 | Fix 4 lỗi consistency | `705d3dc` | Single source of truth cho commission/slippage |
| 2026-04-19 | Live scan load 300 bars | `228b62d` | EMA200 filter active trong scan (trước đây NaN) |
| 2026-04-19 | EMA200 warmup 252 bars trong backtest | `2709e8e` | Filter calibrate trên dữ liệu trước cửa sổ |
| 2026-04-19 | Thêm EMA200 trend filter | `7deba8e` | Chặn BUY khi `close < EMA200` |
| 2026-04-19 | Enforce T+2 cho stop/TP exit | `233f679` | Trước đây bị bypass qua intraday exit |
| 2026-04-19 | Enforce T+2 bằng `sim_date` | `c6e53e1` | Trước đây dùng `date.today()` |
| 2026-04-19 | Fix bug rapid-fire BUY trong backtester | `9750f37` | Entry-bar guard, qty>0 guard, pending guard |
| 2026-04-19 | Implement ban đầu Week 5 | `d9f132d` | SimulatedBroker + Backtester + 13 tests |

---

## 5. Commit Protocol

**Mỗi lần** thay đổi thuật toán (signal weights/thresholds/filters, risk params, execution logic, backtest methodology):

1. **Cập nhật code** trong `signals/`, `core/`, `brokers/`
2. **Cập nhật doc này** — section 1 (algo spec) với giá trị mới
3. **Cập nhật `system-design.md`** nếu architecture thay đổi (ví dụ module mới, thay interface)
4. **Cập nhật `product-spec.md`** nếu strategy philosophy thay đổi (ví dụ Kelly sizing policy, risk budget mới)
5. **Append section 4 (Change Log)** với ngày, commit SHA, mô tả 1 dòng
6. **Nếu đóng 1 roadmap item** (section 3):
   - Đổi `[ ]` → `[x]`
   - Append commit SHA và success metric đo được
7. **Chạy lại VN30 backtest** — `python scripts/backtest_vn30.py`
   - Nếu median alpha thay đổi > 5pp, cập nhật section 2.1 + thêm observation vào 2.3
8. **Một commit cho một thay đổi thuật toán** (Workflow Rule #1 trong CLAUDE.md)

Nếu cần nhiều cải tiến độc lập, tách thành ticket và commit riêng — không bundle.

### Template thay đổi

Khi sửa section 1, dùng comment sau khi xoá/thay rule:

```markdown
<!-- REMOVED 2026-04-22 commit abc1234: RSI>75 gate replaced with soft decay to -1.0 at RSI=80 -->
```

Không được rewrite section 1 một cách âm thầm — luôn để rule bị xoá dưới dạng comment để audit.
