# VN Swing Trading — Nguồn Chính Thống Về Thuật Toán

> **Đây là tài liệu trung tâm về thuật toán đang áp dụng cho hệ thống.**
> Mọi thay đổi về signal, risk, execution, hoặc backtest methodology PHẢI cập nhật file này cùng lúc với code theo [Commit Protocol](#5-commit-protocol) ở cuối file.
>
> **Cập nhật lần cuối**: 2026-04-19 · **Phiên bản baseline**: `MomentumV1 v1.0`
>
> **Quan điểm đánh giá**: đây là **swing trading** trên tài khoản nhỏ (500M VND), cash chung, `max_positions=5`. Không so sánh với buy-and-hold dài hạn — B&H là chiến lược khác, sẽ được đánh giá khi phát triển signal engine riêng cho nó. Metric baseline dùng **portfolio-level**, không phải per-symbol.

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
- **Portfolio simulator** (`scripts/backtest_portfolio_vn30.py`): event loop trên union các ngày giao dịch của VN30, cash chung, `max_positions=5`. Khi > 5 BUY signal trong 1 phiên → rank theo score giảm dần và fill top-K slot còn trống. Đây là script dùng để đánh giá baseline theo **swing trading lens**.
- **Per-symbol backtest** (`scripts/backtest_vn30.py`): chạy độc lập từng symbol với 500M; chỉ dùng để chẩn đoán per-symbol (symbol nào được thuật toán handle tốt/tệ), **không dùng làm baseline chính**.

---

## 2. Hiệu suất baseline

**Setup**: 500M VND, `max_positions=5`, universe VN30 (31 symbols), shared cash pool — mô phỏng đúng swing trading thực tế (nhiều symbol cùng emit signal → rank theo score, chọn top-K fill slot trống).

**Cửa sổ chạy**: 2022-04-22 → 2026-04-17 (3.95 năm thực tế — 1 năm đầu bị warmup tiêu thụ để calibrate EMA200).

**Dữ liệu**:
- `data/backtest_portfolio_vn30_trades.csv` — 227 trades
- `data/backtest_portfolio_vn30_equity.csv` — equity curve theo ngày
- `data/backtest_portfolio_vn30_periodic.csv` — breakdown theo năm/quý

**Phiên bản algo**: `MomentumV1 v1.0` (EMA200 filter bật, R:R 1:3, BUY_THRESHOLD 0.55).

### 2.1 Aggregate Metrics (swing trading lens)

| Metric | Giá trị | Mục tiêu | Status |
|--------|--------:|---------:|:------:|
| Total return | +3.69% | > 50% / 4 năm | ❌ |
| CAGR | +0.92% | > 10%/năm | ❌ |
| Sharpe | 0.141 | > 1.0 | ❌ |
| Sortino | 0.127 | > 1.5 | ❌ |
| Max drawdown | 17.21% | < 15% | ❌ |
| Win rate | 28.63% | > 40% | ❌ |
| Profit factor | 1.038 | > 1.5 | ❌ |
| Avg win | +7.53M VND | — | — |
| Avg loss | -2.91M VND | — | — |
| R:R thực tế (avg_win / |avg_loss|) | 2.59 | ≥ 3.0 | ❌ |
| Tổng trades | 227 (57.5/năm) | ≥ 150 | ✅ |
| Avg hold | 21.7 ngày (median 12) | 5-25 ngày (swing) | ✅ |

**Phân loại exit**:
| Reason | Count | % |
|--------|------:|--:|
| STOP (hit) | 158 | 69.6% |
| TP (hit) | 64 | 28.2% |
| SELL (signal) | 2 | 0.9% |
| EOD (close cuối kỳ) | 3 | 1.3% |

**Tham chiếu**: lãi tiết kiệm VN ~5%/năm → CAGR 0.92% của chiến lược **thấp hơn lãi gửi ngân hàng**. Chiến lược hiện chưa có edge đủ để trả công sức + chi phí giao dịch.

### 2.2 Phân rã theo năm

| Năm | Return | Trades | Win Rate | PnL (M VND) |
|-----|-------:|-------:|---------:|------------:|
| 2022 (Q2-Q4) | **-9.55%** | 15 | 6.67% | -44.3 |
| 2023 | +3.27% | 30 | 23.33% | -2.5 |
| 2024 | +1.78% | 65 | 30.77% | +18.4 |
| 2025 | **+22.08%** | 87 | 36.78% | +104.1 |
| 2026 (YTD) | -10.67% | 30 | 16.67% | -57.8 |

Biến động lớn giữa các năm — **2025 kiếm được +22%, nhưng gần như giao toàn bộ cho 2026 Q1 (-12.84%)**. Chiến lược có momentum nhưng không tự bảo vệ khi regime đảo chiều.

### 2.3 Phân rã theo quý

| Quarter | Return | Trades | WinRate | PnL (M VND) |
|---------|-------:|-------:|--------:|------------:|
| 2022Q2 | -3.38% | 3 | 0.00% | -16.9 |
| 2022Q3 | -1.85% | 8 | 12.50% | -9.0 |
| 2022Q4 | -4.62% | 4 | 0.00% | -18.4 |
| 2023Q1 | +5.36% | 4 | 25.00% | +3.0 |
| 2023Q2 | +1.61% | 2 | 100.00% | +13.7 |
| 2023Q3 | -1.43% | 14 | 21.43% | +2.7 |
| 2023Q4 | -2.14% | 10 | 10.00% | -21.9 |
| 2024Q1 | **+8.49%** | 15 | 66.67% | +45.3 |
| 2024Q2 | -1.77% | 16 | 25.00% | -2.3 |
| 2024Q3 | -1.20% | 14 | 21.43% | -9.9 |
| 2024Q4 | -3.33% | 20 | 15.00% | -14.7 |
| 2025Q1 | -1.94% | 23 | 30.43% | -2.8 |
| 2025Q2 | **+12.52%** | 16 | 43.75% | +52.1 |
| 2025Q3 | **+12.03%** | 22 | 54.55% | +64.0 |
| 2025Q4 | -1.24% | 26 | 23.08% | -9.1 |
| 2026Q1 | **-12.84%** | 25 | 12.00% | -71.4 |
| 2026Q2 | +2.49% | 5 | 40.00% | +13.6 |

**Pattern dễ thấy**: quý kiếm tiền = win rate ≥ 40%; quý lỗ = win rate ≤ 25%. Edge của thuật toán phụ thuộc hoàn toàn vào việc thị trường có "chiều lòng" momentum strategy hay không. 10/17 quý có return âm.

### 2.4 Quan sát chính

1. **70% trade bị stop-out** (158/227) — momentum signal kích hoạt quá nhiều false-positive. BUY_THRESHOLD 0.55 không đủ lọc, đặc biệt trong regime SIDEWAYS/choppy.
2. **R:R thực tế 2.59 (vs thiết kế 3.0)** — TP hit ít, stop hit nhiều, slippage + commission ăn bớt reward. Muốn PF > 1.5 cần hoặc tăng win rate lên ~38% hoặc tăng avg_win thêm 40%.
3. **Momentum chạy theo market regime** — 2025 (bull) +22%, 2026Q1 (reversal) -12.8%. Thiếu macro filter để tắt signal trong bear regime.
4. **Win rate kém trong bear** — 2022 WR 6.67%, 2026Q1 WR 12% vs 2024Q1 WR 66.67%, 2025Q3 WR 54.55%. EMA200 filter không đủ — cần thêm filter ở tầng thị trường (VN30 basket EMA50) để nhận diện bear sớm.
5. **Hold 21.7 ngày trung bình (median 12)** — đúng tính chất swing, không phải day-trade (< 3 ngày) cũng không phải position-trade (> 60 ngày). T+2 không phải rào cản.
6. **Capacity chưa dùng hết** — portfolio chạy với max 5 slot nhưng 57.5 trades/năm ≈ ~11 trades/slot/năm, tức các slot thường trống. Có thể do BUY_THRESHOLD quá cao hoặc eligibility filter quá strict.
7. **CAGR < lãi tiết kiệm** — 0.92%/năm không xứng với rủi ro MDD 17%. Chiến lược chưa có edge đủ để triển khai thật, cần cải tiến trọng tâm ở exit + macro filter trước khi chuyển Phase 2.

---

## 3. Roadmap cải tiến

Status: `[ ]` todo · `[~]` đang làm · `[x]` xong (kèm commit SHA + impact đo được)

> **Tất cả success criteria đều đo ở portfolio level** (script `backtest_portfolio_vn30.py`), so sánh với baseline hiện tại: CAGR +0.92%, Sharpe 0.141, MDD 17.21%, WR 28.63%, PF 1.038.

### 3.1 Market-Level Filters

- [ ] **VN30 macro regime filter** — tính basket VN30 equal-weight và EMA50; chặn BUY mới khi basket < basket EMA50
  - **Rationale**: 70% tương quan giữa cổ phiếu VN30 và basket. Năm 2022 và 2026Q1 lỗ nặng do algo tiếp tục BUY trong bear. EMA200 per-symbol không đủ — cần filter ở tầng thị trường.
  - **Impact dự kiến**: giảm trades trong bear period; cải thiện WR và MDD.
  - **Success**: WR tổng ≥ 35% và WR trong bear quarter ≥ 25% (hiện 6-16%), MDD ≤ 12%
- [ ] **Relative strength vs VN30 basket** — chỉ BUY khi return(20d) của symbol > return(20d) của basket
  - **Rationale**: Swing momentum cần leadership so với thị trường; BUY leader thay vì laggard giảm stop-out rate.
  - **Success**: STOP/TP ratio giảm từ 2.47 (158/64) xuống ≤ 1.5

### 3.2 Entry Refinement

- [ ] **Xác nhận volume breakout** — yêu cầu `vol > 150% × vol_MA20` trên signal bar
  - **Rationale**: weight volume 0.10 hiện tại cho phép BUY trên volume yếu. Momentum không có volume = chop → stop-out.
  - **Success**: WR ≥ 35% (hiện 28.63%), số trades giảm không quá 30%
- [ ] **Yêu cầu MACD zero-line** — thêm hard gate: MACD line phải > 0 mới BUY (không chỉ > signal)
  - **Rationale**: gate hiện tại cho phép BUY khi cả MACD & signal đều âm (vẫn downtrend).
  - **Success**: WR tổng ≥ 33%, quý lỗ giảm từ 10/17 xuống ≤ 7/17
- [ ] **Tránh BUY cuối phiên** (chỉ live scan) — scan lúc 15:35, nhưng tag signal > 14:45 là "late" và yêu cầu score > 0.65 thay vì 0.55
  - **Rationale**: Late-session rally hay gap down sáng hôm sau.
  - **Success**: Avg gap-down loss giảm (đo qua log live scan Phase 1 sau 30 trades)

### 3.3 Exit Refinement (impact lớn nhất)

- [ ] **Trailing stop sau +1R** — khi unrealized gain > 1R (= 1.5×ATR), trail stop tại `high - 2×ATR`; bỏ TP cố định
  - **Rationale**: TP hit chỉ 28% (64/227), nhiều winner bị chốt sớm. Trailing cho phép winner chạy trong trend mạnh.
  - **Impact dự kiến**: Lớn nhất — avg_win có thể tăng ≥ 50%.
  - **Success**: Profit factor ≥ 1.3, CAGR ≥ 5%/năm
- [ ] **TP thích nghi theo regime** — TRENDING: giữ ATR×4.5 hoặc trailing; SIDEWAYS: giảm còn ATR×2; VOLATILE: giảm còn ATR×1.5
  - **Rationale**: Sideways cho lại profit nhanh — chốt sớm. Nhiều quý (2023Q3, 2024Q2-Q4) lỗ do thị trường sideways.
  - **Success**: WR trong SIDEWAYS ≥ 35%, PF trong SIDEWAYS > 1.0
- [ ] **Breakeven stop sau +1R** — kéo stop về entry khi đạt +1R (bảo vệ chống lỗ)
  - **Rationale**: thay đổi nhỏ, ngăn winning-to-loss flip. 158 stop-out hiện tại có thể giảm đáng kể.
  - **Success**: Avg loss giảm 20% (từ -2.91M xuống ≤ -2.33M)

### 3.4 Position Sizing

- [ ] **Kelly fraction từ 30-trade rolling** — sau 30 trades, dùng `half-Kelly = 0.5 × (W - (1-W)/R)` giới hạn ở 2%
  - **Rationale**: 2% cố định hiện tại không thích nghi với edge quan sát được (đặc biệt trong bear period nên giảm size).
  - **Success**: CAGR ≥ +3%/năm mà MDD không tăng > 2pp
- [ ] **Risk điều chỉnh theo volatility** — regime VOLATILE: giảm `RISK_PCT` xuống 1% (từ 2%)
  - **Rationale**: Volatile = stop dễ bị hit; giảm size bảo vệ vốn.
  - **Success**: MDD ≤ 12%

### 3.5 Portfolio-Level

- [ ] **Giới hạn concentration theo sector** — tối đa 2 vị thế mở cùng sector (ngân hàng, BĐS, thép, bán lẻ)
  - **Rationale**: VN30 có 6-7 ngân hàng + 4-5 BĐS. Tương quan nội ngành cao → nhiều lúc 5 slot cùng chịu rủi ro tương tự.
  - **Success**: MDD ≤ 12%, daily return std giảm ≥ 15%
- [ ] **Lọc vị thế theo correlation** — từ chối BUY mới nếu `corr(20d, existing_positions) > 0.7`
  - **Rationale**: Phiên bản thống kê của sector filter.
  - **Success**: equity curve mượt hơn (max consecutive down-days giảm ≥ 20%)

### 3.6 Signal Engine Extensions (Phase 2+)

- [ ] **Foreign flow từ SSI** — khi Phase 2 có SSI integration, tăng foreign-flow weight từ 0.05 → 0.15
  - **Rationale**: Foreign flow là leading indicator mạnh ở VN; 0.05 quá thấp.
  - **Success**: WR ≥ 38%
- [ ] **Intraday volume profile** — giữa phiên (≥ 10:30) check cumulative vol > 50% projected daily vol trước khi vào lệnh
  - **Rationale**: Xác nhận momentum sớm hơn trong phiên.

### 3.7 Validation Mô Hình

- [ ] **Stress test crash 2022** — backtest riêng cửa sổ Q2-Q3 2022
  - **Success**: MDD trong period đó < 10%, quarterly return ≥ -2%
- [ ] **Parameter sensitivity grid** — sweep BUY_THRESHOLD ∈ {0.45, 0.50, 0.55, 0.60, 0.65} × ATR_TP_MULT ∈ {2, 3, 4.5, 6, trailing}
  - **Success**: xác định flat plateau (robust) vs sharp peak (overfit)
- [ ] **Walk-forward re-validation** — sau khi implement Top-3 cải tiến, chạy lại portfolio backtest với IS/OOS split
  - **Success**: IS/OOS Sharpe lệch < 0.3

### 3.8 Thứ tự ưu tiên (đề xuất)

Dựa trên **impact dự kiến × độ dễ implement**, nhắm vào 2 vấn đề lớn nhất của baseline: **WR thấp (28.63%)** và **bear-period bleed (2022, 2026Q1)**:

1. 🔥 **VN30 macro filter** (3.1) — fix vấn đề lớn nhất: bear-period bleed. Đơn giản, tác động trực tiếp đến WR + MDD.
2. 🔥 **Trailing stop sau +1R** (3.3) — cải thiện avg_win và PF; 70% trade bị stop nghĩa là nhiều winner không kịp biến thành big winner.
3. 🔥 **Xác nhận volume breakout** (3.2) — lọc nhanh nhất để tăng WR từ 28% → 35%+.
4. **TP thích nghi theo regime** (3.3) — giảm lỗ trong SIDEWAYS (chiếm phần lớn các quý âm).
5. **Relative strength vs VN30 basket** (3.1) — focus vào leader.
6. **Giới hạn concentration sector** (3.5) — giảm correlation ẩn, smoother equity.

---

## 4. Change Log

| Ngày | Thay đổi | Commit | Ghi chú |
|------|----------|--------|---------|
| 2026-04-19 | **Portfolio baseline (swing trading lens)** | `012d39f` | Shared cash 500M, max_positions=5, CAGR +0.92%, WR 28.63%, MDD 17.21%. Bỏ B&H comparison. |
| 2026-04-19 | Dịch doc sang tiếng Việt | `78447bc` | Giữ nguyên tên metric/constant |
| 2026-04-19 | SSoT doc + baseline per-symbol (đã deprecate) | `87af473` | Per-symbol kết quả còn trong `data/backtest_vn30_2021-2026.csv` — chỉ dùng chẩn đoán |
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
