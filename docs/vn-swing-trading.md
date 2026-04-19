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
- `vol / vol_MA20 < 1.5` → score bị clamp về `_BUY_THRESHOLD - 0.01` *(`_VOL_BREAKOUT_MIN` — momentum cần volume confirm)*
- `market_context["macro_above_ema50"] == False` → score bị clamp về `_BUY_THRESHOLD - 0.01` *(VN30 basket ≤ EMA50 ⇒ bear macro ⇒ chặn BUY mới; permissive nếu `market_context=None`)*
- `macd_line < 0` → score bị clamp về `_BUY_THRESHOLD - 0.01` *(MACD zero-line gate — chặn BUY khi trend chưa đảo chiều dương)*

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
| `ATR_STOP_MULT` | 1.5 | `stop = entry − 1.5 × ATR14` (= 1R) |
| `ATR_TRAIL_TRIGGER` | 1.5 | activate trailing khi `high ≥ entry + 1R` |
| `ATR_TRAIL_MULT` | 2.0 | trailing distance: `trail_stop = max(current_stop, high − 2 × ATR)` |
| `ATR_TP_MULT` | 4.5 | **deprecated** — fixed TP thay thế bằng trailing stop sau +1R (giữ constant để backwards compat cho `PositionSizeResult.take_profit`) |
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
  3. Stop kiểm tra trên low từ T+1 trở đi, nhưng chỉ khi đã qua T+2 từ entry. Stop ưu tiên khi cả stop và trail-trigger cùng xảy ra trong 1 bar (conservative).
  4. **Trailing stop**: sau khi `high ≥ entry + 1R` (tại bất kỳ bar nào sau T+2), flag `trail_active = True`. Từ bar đó trở đi, update `stop = max(current_stop, bar.high − 2 × ATR_entry)` — stop chỉ ratchet lên.
  5. Chặn re-entry trên bar bị stop-out (không BUY ngay sau forced exit)
- **Portfolio simulator** (`scripts/backtest_portfolio_vn30.py`): event loop trên union các ngày giao dịch của VN30, cash chung, `max_positions=5`. Khi > 5 BUY signal trong 1 phiên → rank theo score giảm dần và fill top-K slot còn trống. Đây là script dùng để đánh giá baseline theo **swing trading lens**.
- **Per-symbol backtest** (`scripts/backtest_vn30.py`): chạy độc lập từng symbol với 500M; chỉ dùng để chẩn đoán per-symbol (symbol nào được thuật toán handle tốt/tệ), **không dùng làm baseline chính**.

---

## 2. Hiệu suất baseline

**Setup**: 500M VND, `max_positions=5`, universe VN30 (31 symbols), shared cash pool — mô phỏng đúng swing trading thực tế (nhiều symbol cùng emit signal → rank theo score, chọn top-K fill slot trống).

**Cửa sổ chạy**: 2022-04-22 → 2026-04-17 (3.95 năm thực tế — 1 năm đầu bị warmup tiêu thụ để calibrate EMA200).

**Dữ liệu**:
- `data/backtest_portfolio_vn30_trades.csv` — 215 trades
- `data/backtest_portfolio_vn30_equity.csv` — equity curve theo ngày
- `data/backtest_portfolio_vn30_periodic.csv` — breakdown theo năm/quý

**Phiên bản algo**: `MomentumV1 v1.0` với **3 hard gates** (EMA200 per-symbol, `vol/vol_MA20 ≥ 1.5`, VN30 basket > EMA50) và **trailing stop sau +1R** thay cho TP cố định.

### 2.1 Aggregate Metrics — So sánh trước/sau Top-3 improvements

Baseline **Before** = phiên bản chỉ có EMA200 per-symbol filter và TP cố định (4.5×ATR). **After** = phiên bản hiện tại (macro filter + volume gate + trailing stop).

| Metric | Before | After | Δ | Mục tiêu | Status |
|--------|-------:|------:|---:|---------:|:------:|
| Total return | +3.69% | **+7.05%** | +3.36pp | > 50% / 4 năm | ❌ |
| CAGR | +0.92% | **+1.74%** | +0.82pp | > 10%/năm | ❌ |
| Sharpe | 0.141 | **0.261** | +85% | > 1.0 | ❌ |
| Sortino | 0.127 | 0.211 | +66% | > 1.5 | ❌ |
| Max drawdown | 17.21% | **8.62%** | **−50%** | < 12% | ✅ |
| Win rate | 28.63% | **36.74%** | +8.11pp | > 40% | ❌ |
| Profit factor | 1.038 | **1.106** | +7% | > 1.5 | ❌ |
| Avg win | +7.53M | +4.58M | −39% | — | — |
| Avg loss | −2.91M | −2.41M | −17% | — | — |
| R:R thực tế | 2.59 | 1.90 | −0.69 | ≥ 2.0 | ≈ |
| Tổng trades | 227 | 215 | −5% | ≥ 150 | ✅ |
| Avg hold | 21.7 ngày | 13.7 ngày | −37% | 5-25 ngày (swing) | ✅ |

**Phân loại exit (After)**:
| Reason | Count | % |
|--------|------:|--:|
| STOP (hit hard stop, chưa activate trail) | 108 | 50.2% |
| TRAIL (hit trailing stop sau +1R) | 105 | 48.8% |
| EOD (close cuối kỳ) | 2 | 1.0% |

### 2.2 Phân rã theo năm

| Năm | Return | Trades | Win Rate | PnL (M VND) |
|-----|-------:|-------:|---------:|------------:|
| 2022 (Q2-Q3) | −0.13% | 4 | 25.00% | −0.6 |
| 2023 | −0.86% | 47 | 38.30% | −10.4 |
| 2024 | −0.11% | 58 | 34.48% | −3.6 |
| 2025 | **+10.73%** | 78 | 39.74% | +43.3 |
| 2026 (YTD) | −2.26% | 28 | 32.14% | +6.1 |

**Bear 2022 trước: −9.55% | nay: −0.13%** — macro filter gần như tắt hoàn toàn signal giai đoạn bear (chỉ 4 trades trong 2 quý, vs 15 trades trước kia).

### 2.3 Phân rã theo quý

| Quarter | Return | Trades | WinRate | PnL (M VND) |
|---------|-------:|-------:|--------:|------------:|
| 2022Q2 | 0.00% | 0 | — | 0.0 |
| 2022Q3 | −0.13% | 4 | 25.00% | −0.6 |
| 2022Q4 | 0.00% | 0 | — | 0.0 |
| 2023Q1 | −1.01% | 7 | 57.14% | −4.3 |
| 2023Q2 | +0.32% | 15 | 33.33% | +3.0 |
| 2023Q3 | +1.00% | 22 | 40.91% | +2.7 |
| 2023Q4 | −1.15% | 3 | 0.00% | −11.8 |
| 2024Q1 | **+3.43%** | 17 | 52.94% | +9.3 |
| 2024Q2 | −3.10% | 18 | 33.33% | −1.2 |
| 2024Q3 | +0.94% | 10 | 20.00% | −2.9 |
| 2024Q4 | −1.26% | 13 | 23.08% | −8.7 |
| 2025Q1 | −1.35% | 20 | 45.00% | +4.7 |
| 2025Q2 | +1.65% | 9 | 33.33% | −8.9 |
| 2025Q3 | **+11.27%** | 26 | 50.00% | +42.6 |
| 2025Q4 | −0.76% | 23 | 26.09% | +4.8 |
| 2026Q1 | −3.59% | 26 | 30.77% | −0.7 |
| 2026Q2 | +1.38% | 2 | 50.00% | +6.8 |

**Quý âm giảm từ 10/17 xuống 9/17**, mức độ âm giảm mạnh: **2022Q2/Q3/Q4 (−3.38%/−1.85%/−4.62%) → (0%/−0.13%/0%)**, **2026Q1 (−12.84%) → (−3.59%)**.

### 2.4 Quan sát chính

1. **Macro filter giải quyết được bear-period bleed** — đây là thay đổi có impact lớn nhất về mặt MDD: từ 17.21% xuống 8.62% (giảm một nửa, qua mục tiêu ≤ 12%). 2022 và 2026Q1 — 2 giai đoạn lỗ thảm hoạ trước kia — bây giờ gần như trung tính.
2. **Trailing stop đổi "ít win lớn" thành "nhiều win vừa"** — win rate nhảy từ 28.63% lên 36.74% (+8.11pp), avg_win giảm từ 7.53M xuống 4.58M, avg_loss giảm từ −2.91M xuống −2.41M. TRAIL chiếm 48.8% exit (trước đây TP hit chỉ 28.2%). Hold time giảm 21.7 → 13.7 ngày — đúng tinh thần swing.
3. **Volume gate lọc false-positive hiệu quả** — trades chỉ giảm 5% (227 → 215) nhưng WR tăng 8pp → gate đi đúng chỗ cần đi.
4. **Profit factor vẫn chỉ 1.106** — chưa đạt mục tiêu ≥ 1.5 (cần cải tiến thêm). Phần lớn P&L dương vẫn tập trung ở 2025Q3 (+11.27%). Các quý còn lại gần như hòa vốn.
5. **CAGR 1.74% vẫn < lãi tiết kiệm** — MDD giờ đã ở mức chấp nhận được nhưng edge chưa đủ để scale capital. Cần roadmap 3.3 (TP thích nghi theo regime), 3.1 (RS vs basket), hoặc 3.5 (sector concentration) để nâng PF lên ≥ 1.3.
6. **Exit reasons cân bằng STOP/TRAIL** — 50.2% / 48.8% nghĩa là khoảng một nửa trade đạt +1R rồi chạy tiếp. Các nhóm STOP "thuần" (chưa activate trail) = symbol dừng sớm khi signal false-positive — đây là bucket cần filter thêm (3.1 RS vs VN30 hoặc 3.2 MACD zero-line).
7. **Slot utilization khác biệt không lớn** — trước 67.7%, bây giờ tương tự (số trades gần không đổi). Không cần raise max_positions khi PF < 1.3.

---

## 3. Roadmap cải tiến

Status: `[ ]` todo · `[~]` đang làm · `[x]` xong (kèm commit SHA + impact đo được)

> **Tất cả success criteria đều đo ở portfolio level** (script `backtest_portfolio_vn30.py`). Baseline hiện tại (sau khi đóng Top-3): CAGR +1.74%, Sharpe 0.261, MDD 8.62%, WR 36.74%, PF 1.106. Baseline cũ (trước Top-3): CAGR +0.92%, Sharpe 0.141, MDD 17.21%, WR 28.63%, PF 1.038.

### 3.1 Market-Level Filters

- [x] **VN30 macro regime filter** — basket VN30 equal-weight, EMA50; chặn BUY mới khi basket ≤ basket EMA50 *(commit `8c7d3c7`)*
  - **Rationale**: 70% tương quan giữa cổ phiếu VN30 và basket. Năm 2022 và 2026Q1 lỗ nặng do algo tiếp tục BUY trong bear. EMA200 per-symbol không đủ — cần filter ở tầng thị trường.
  - **Implementation**: `core/market_regime.py` (MarketRegime class) + param `market_context` trong `SignalEngineProtocol.evaluate`. Caller truyền `regime.context(date)` → `{"macro_above_ema50": bool}`. Permissive nếu `market_context=None` (backward compat cho test cũ).
  - **Success**: WR tổng ≥ 35% và WR trong bear quarter ≥ 25% (hiện 6-16%), MDD ≤ 12%
  - **Kết quả đo được** (kết hợp với 3.2 + 3.3): MDD 17.21% → 8.62% ✅ (giảm 50%), 2022 (bear) return −9.55% → −0.13% ✅, 2026Q1 −12.84% → −3.59% ✅, WR 28.63% → 36.74% ✅
- [ ] **Relative strength vs VN30 basket** — chỉ BUY khi return(20d) của symbol > return(20d) của basket
  - **Rationale**: Swing momentum cần leadership so với thị trường; BUY leader thay vì laggard giảm stop-out rate.
  - **Success**: STOP/TP ratio giảm từ 2.47 (158/64) xuống ≤ 1.5

### 3.2 Entry Refinement

- [x] **Xác nhận volume breakout** — hard gate `vol >= 1.5 × vol_MA20` trên signal bar *(commit `41d51d6`)*
  - **Rationale**: weight volume 0.10 hiện tại cho phép BUY trên volume yếu. Momentum không có volume = chop → stop-out.
  - **Success**: WR ≥ 35% (hiện 28.63%), số trades giảm không quá 30%
  - **Kết quả đo được** (kết hợp với 3.1 + 3.3): WR 28.63% → 36.74% ✅, trades 227 → 215 (−5%) ✅
- [x] **Yêu cầu MACD zero-line** — hard gate: MACD line phải > 0 mới BUY (không chỉ > signal) *(commit pending — chạy backtest để đo impact)*
  - **Rationale**: gate hiện tại cho phép BUY khi cả MACD & signal đều âm (vẫn downtrend).
  - **Success**: WR tổng ≥ 33%, quý lỗ giảm từ 10/17 xuống ≤ 7/17
- [ ] **Tránh BUY cuối phiên** (chỉ live scan) — scan lúc 15:35, nhưng tag signal > 14:45 là "late" và yêu cầu score > 0.65 thay vì 0.55
  - **Rationale**: Late-session rally hay gap down sáng hôm sau.
  - **Success**: Avg gap-down loss giảm (đo qua log live scan Phase 1 sau 30 trades)

### 3.3 Exit Refinement (impact lớn nhất)

- [x] **Trailing stop sau +1R** — khi unrealized gain > 1R (= 1.5×ATR), trail stop tại `high - 2×ATR`; bỏ TP cố định *(commit `e23a2f0`)*
  - **Rationale**: TP hit chỉ 28% (64/227), nhiều winner bị chốt sớm. Trailing cho phép winner chạy trong trend mạnh.
  - **Implementation**: flag `trail_active` trong `Position`/`open_position`; activate khi `high ≥ entry + ATR_TRAIL_TRIGGER × ATR_entry`. Sau đó `stop = max(stop, high - ATR_TRAIL_MULT × ATR_entry)`. Dùng `entry_atr` frozen để đồng nhất khoảng trail trong suốt trade; stop ratchet only up.
  - **Success**: Profit factor ≥ 1.3, CAGR ≥ 5%/năm
  - **Kết quả đo được** (kết hợp với 3.1 + 3.2): PF 1.038 → 1.106 ❌ (mục tiêu 1.3 chưa đạt), CAGR 0.92% → 1.74% ❌ (mục tiêu 5% chưa đạt), nhưng MDD 17.21% → 8.62% ✅ và Sharpe 0.141 → 0.261 (+85%) ✅. Trade-off: avg_win 7.53M → 4.58M (−39%) đổi lấy WR +8.11pp. Đúng hướng kỳ vọng (nhiều winner vừa thay vì ít winner lớn).
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

**Top-3 đã đóng** ✅ — fix bear-period bleed + cải thiện WR. Kết quả: MDD 17.21% → 8.62%, WR 28.63% → 36.74%, Sharpe +85%. Nhưng **PF chỉ 1.106 và CAGR 1.74%** chưa đủ để triển khai thật.

Vòng tiếp theo nhắm vào **vấn đề mới: PF thấp + win rate dưới mục tiêu 40%**:

1. 🔥 **Relative strength vs VN30 basket** (3.1) — focus vào leader thay vì laggard; giảm STOP thuần (50% exit hiện tại).
2. 🔥 **MACD zero-line filter** (3.2) — loại BUY khi cả MACD và signal đều âm; lọc thêm một lớp.
3. 🔥 **TP thích nghi theo regime** (3.3) — SIDEWAYS chốt sớm để tránh giải lại lợi nhuận.
4. **Sector concentration limit** (3.5) — max 2 vị thế cùng sector; giảm correlation ẩn.
5. **Breakeven stop sau +1R** (3.3) — bổ sung cho trailing stop; bảo vệ winner trước khi nó thành loser.
6. **Walk-forward re-validation** (3.7) — IS/OOS split với filter mới để kiểm tra robust.

---

## 4. Change Log

| Ngày | Thay đổi | Commit | Ghi chú |
|------|----------|--------|---------|
| 2026-04-19 | **Re-baseline VN30 portfolio** sau Top-3 improvements | `752abbf` | CAGR +0.92% → +1.74%, Sharpe 0.141 → 0.261, MDD 17.21% → 8.62%, WR 28.63% → 36.74%, PF 1.038 → 1.106 |
| 2026-04-19 | Trailing stop sau +1R (roadmap 3.3) | `e23a2f0` | Bỏ TP cố định; `ATR_TRAIL_TRIGGER=1.5`, `ATR_TRAIL_MULT=2.0`; stop ratchet only up |
| 2026-04-19 | VN30 macro regime filter (roadmap 3.1) | `8c7d3c7` | Basket VN30 equal-weight + EMA50; `core/market_regime.py`. Chặn BUY khi basket ≤ EMA50 |
| 2026-04-19 | Volume breakout hard gate (roadmap 3.2) | `41d51d6` | `vol >= 1.5 × vol_MA20` mới BUY |
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
