# VN Swing Trading — Nguồn Chính Thống Về Thuật Toán

> **Đây là tài liệu trung tâm về thuật toán đang áp dụng cho hệ thống.**
> Mọi thay đổi về signal, risk, execution, hoặc backtest methodology PHẢI cập nhật file này cùng lúc với code theo [Commit Protocol](#5-commit-protocol) ở cuối file.
>
> **Cập nhật lần cuối**: 2026-04-20 · **Phiên bản hiện tại**: `MomentumV1 v1.2`
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

### 1.1 Signal Engine — `MomentumV1 v1.2`

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
- `return20d(symbol) ≤ basket_return_20d` → score bị clamp về `_BUY_THRESHOLD - 0.01` *(RS gate — chặn BUY khi symbol underperform VN30 basket 20 ngày; permissive nếu `basket_return_20d` không có trong `market_context`)*

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
- `data/backtest_portfolio_vn30_trades.csv` — 179 trades
- `data/backtest_portfolio_vn30_equity.csv` — equity curve theo ngày
- `data/backtest_portfolio_vn30_periodic.csv` — breakdown theo năm/quý

**Phiên bản algo**: `MomentumV1 v1.2` — v1.1 với adaptive TP disabled (pending tuning). Gates active: EMA200, volume ≥1.5×, macro EMA50, MACD>0, RS>basket, breakeven stop, sector limit.

### 2.1 Aggregate Metrics — So sánh qua các phiên bản

| Metric | v1.0 Before | v1.0 After (Top-3) | v1.1 (w/ adaptive TP) | **v1.2 (hiện tại)** | Mục tiêu | Status |
|--------|------------:|-------------------:|----------------------:|--------------------:|---------:|:------:|
| Total return | +3.69% | +7.05% | −2.88% | **+16.46%** | > 50% / 4 năm | ❌ |
| CAGR | +0.92% | +1.74% | −0.74% | **+3.94%** | > 10%/năm | ❌ |
| Sharpe | 0.141 | 0.261 | −0.079 | **0.550** | > 1.0 | ❌ |
| Sortino | 0.127 | 0.211 | −0.061 | **0.463** | > 1.5 | ❌ |
| Max drawdown | 17.21% | 8.62% | 9.86% | **7.91%** | < 12% | ✅ |
| Win rate | 28.63% | 36.74% | 42.73% | **38.55%** | > 40% | ❌ |
| Profit factor | 1.038 | 1.106 | 0.957 | **1.281** | > 1.5 | ❌ |
| Avg win | +7.53M | +4.58M | +3.37M | **+5.40M** | — | — |
| Avg loss | −2.91M | −2.41M | −2.63M | **−2.64M** | — | — |
| R:R thực tế | 2.59 | 1.90 | 1.28 | **2.04** | ≥ 2.0 | ✅ |
| Tổng trades | 227 | 215 | 227 | **179** | ≥ 150 | ✅ |
| Avg hold | 21.7 ngày | 13.7 ngày | 9.5 ngày | **13.5 ngày** | 5-25 ngày (swing) | ✅ |

**Phân loại exit (v1.2)**:
| Reason | Count | % |
|--------|------:|--:|
| TRAIL (hit trailing stop sau +1R) | 91 | 50.8% |
| STOP (hit hard stop, chưa activate trail) | 86 | 48.0% |
| EOD (close cuối kỳ) | 2 | 1.1% |

### 2.2 Phân rã theo năm

| Năm | Return | Trades | Win Rate | PnL (M VND) |
|-----|-------:|-------:|---------:|------------:|
| 2022 (Q2-Q3) | +0.39% | 3 | 33.33% | +1.9 |
| 2023 | −3.02% | 41 | 34.15% | −15.1 |
| 2024 | +2.72% | 43 | 34.88% | +4.5 |
| 2025 | **+18.67%** | 66 | 43.94% | +80.7 |
| 2026 (YTD) | −1.88% | 26 | 38.46% | +9.8 |

### 2.3 Phân rã theo quý (v1.2)

| Quarter | Return | Trades | WinRate | PnL (M VND) |
|---------|-------:|-------:|--------:|------------:|
| 2022Q2 | 0.00% | 0 | — | 0.0 |
| 2022Q3 | +0.39% | 3 | 33.33% | +1.9 |
| 2022Q4 | 0.00% | 0 | — | 0.0 |
| 2023Q1 | −1.44% | 6 | 50.00% | −4.9 |
| 2023Q2 | +0.82% | 12 | 41.67% | +3.5 |
| 2023Q3 | +0.10% | 18 | 33.33% | −1.3 |
| 2023Q4 | −2.50% | 5 | 0.00% | −12.5 |
| 2024Q1 | **+3.96%** | 11 | 54.55% | +3.7 |
| 2024Q2 | −3.07% | 15 | 33.33% | +0.8 |
| 2024Q3 | +3.01% | 7 | 28.57% | +4.4 |
| 2024Q4 | −1.03% | 10 | 20.00% | −4.4 |
| 2025Q1 | −0.30% | 18 | 55.56% | +9.8 |
| 2025Q2 | +1.48% | 7 | 28.57% | −7.8 |
| 2025Q3 | **+16.42%** | 21 | 57.14% | +59.3 |
| 2025Q4 | +0.75% | 20 | 25.00% | +19.4 |
| 2026Q1 | −3.26% | 24 | 37.50% | +2.1 |
| 2026Q2 | +1.43% | 2 | 50.00% | +7.7 |

**Quý âm: 8/17** (giảm từ 9/17 ở v1.0 After, 10/17 ở v1.0 Before).

### 2.4 Quan sát chính (v1.2)

1. **Bước nhảy vọt so với v1.0**: CAGR +1.74% → **+3.94%**, Sharpe 0.261 → **0.550**, MDD 8.62% → **7.91%**, PF 1.106 → **1.281**. Đây là kết quả tốt nhất từ trước đến nay — lần đầu tiên MDD < 8%.
2. **MACD + RS gate lọc đúng** — trades giảm từ 215 → 179 (−17%) nhưng avg_win tăng từ 4.58M → 5.40M (+18%) và R:R vượt mục tiêu 2.0 (2.04). Hai gate này đang lọc đúng false-positive mà không cắt winner.
3. **Breakeven stop hoạt động hiệu quả** — avg_loss −2.64M (ổn định so với v1.0 After −2.41M), STOP exits giảm từ 108 → 86 (-21%). TRAIL/STOP ratio gần 50/50 — tương tự baseline nhưng ít trades hơn.
4. **Sector limit có net positive effect** — kết hợp với RS gate, việc giảm bank-dominated positions (+2 max) buộc algo chọn symbol tốt hơn toàn universe, không chỉ fill đủ slots với bank.
5. **2025Q3 vẫn là outlier lớn** — +16.42% trong 1 quý (21 trades, WR 57%). P&L 2025 chiếm phần lớn tổng gain. Cần kiểm tra robustness: nếu loại 2025Q3, CAGR còn lại ~0%.
6. **2023Q4 và 2026Q1 vẫn là điểm yếu** — 0% WR (5 trades) và −3.26% (24 trades). Cần phân tích macro context trong các giai đoạn này.
7. **Win rate 38.55% — thấp hơn mục tiêu 40%** — trade-off với R:R 2.04. Cần quyết định: tăng WR hay tăng R:R? Với R:R ≥ 2.0, WR 38% là viable (breakeven WR = 1/(1+RR) ≈ 33%).
8. **Adaptive TP vẫn là open question** — disabled do cắt sớm TRAIL exits. Cần test với `SIDEWAYS_TP_MULT ∈ {3.0, 4.0}` khi có thời gian.

---

## 3. Roadmap cải tiến

Status: `[ ]` todo · `[~]` đang làm · `[x]` xong (kèm commit SHA + impact đo được)

> **Tất cả success criteria đều đo ở portfolio level** (script `backtest_portfolio_vn30.py`). **Baseline hiện tại (v1.2)**: CAGR +3.94%, Sharpe 0.550, MDD 7.91%, WR 38.55%, PF 1.281, R:R 2.04. Baseline v1.0 After (Top-3): CAGR +1.74%, Sharpe 0.261, MDD 8.62%, WR 36.74%, PF 1.106.

### 3.1 Market-Level Filters

- [x] **VN30 macro regime filter** — basket VN30 equal-weight, EMA50; chặn BUY mới khi basket ≤ basket EMA50 *(commit `8c7d3c7`)*
  - **Rationale**: 70% tương quan giữa cổ phiếu VN30 và basket. Năm 2022 và 2026Q1 lỗ nặng do algo tiếp tục BUY trong bear. EMA200 per-symbol không đủ — cần filter ở tầng thị trường.
  - **Implementation**: `core/market_regime.py` (MarketRegime class) + param `market_context` trong `SignalEngineProtocol.evaluate`. Caller truyền `regime.context(date)` → `{"macro_above_ema50": bool}`. Permissive nếu `market_context=None` (backward compat cho test cũ).
  - **Success**: WR tổng ≥ 35% và WR trong bear quarter ≥ 25% (hiện 6-16%), MDD ≤ 12%
  - **Kết quả đo được** (kết hợp với 3.2 + 3.3): MDD 17.21% → 8.62% ✅ (giảm 50%), 2022 (bear) return −9.55% → −0.13% ✅, 2026Q1 −12.84% → −3.59% ✅, WR 28.63% → 36.74% ✅
- [x] **Relative strength vs VN30 basket** — chỉ BUY khi return(20d) của symbol > return(20d) của basket *(commit `1ddbf43`)*
  - **Rationale**: Swing momentum cần leadership so với thị trường; BUY leader thay vì laggard giảm stop-out rate.
  - **Implementation**: `MarketRegime.basket_return_20d(date)` → thêm vào `context()` dict. Hard gate trong `MomentumV1.evaluate()`: `sym_return_20d ≤ basket_return_20d` → clamp. Permissive khi `basket_return_20d` không có trong context.
  - **Kết quả đo được** (v1.2, kết hợp MACD gate + breakeven + sector limit): trades 215 → 179 (−17%), avg_win 4.58M → 5.40M (+18%), R:R 1.90 → 2.04 ✅, PF 1.106 → 1.281 ✅
  - **Success**: STOP/TP ratio — đã đổi metric do bỏ TP cố định; thay bằng STOP/TRAIL ratio: 86/91 ≈ 0.95 (cải thiện từ 108/105 ≈ 1.03)

### 3.2 Entry Refinement

- [x] **Xác nhận volume breakout** — hard gate `vol >= 1.5 × vol_MA20` trên signal bar *(commit `41d51d6`)*
  - **Rationale**: weight volume 0.10 hiện tại cho phép BUY trên volume yếu. Momentum không có volume = chop → stop-out.
  - **Success**: WR ≥ 35% (hiện 28.63%), số trades giảm không quá 30%
  - **Kết quả đo được** (kết hợp với 3.1 + 3.3): WR 28.63% → 36.74% ✅, trades 227 → 215 (−5%) ✅
- [x] **Yêu cầu MACD zero-line** — hard gate: MACD line phải > 0 mới BUY (không chỉ > signal) *(commit `228cda5`)*
  - **Rationale**: gate hiện tại cho phép BUY khi cả MACD & signal đều âm (vẫn downtrend).
  - **Kết quả đo được** (v1.2, kết hợp với RS gate + breakeven + sector limit): quý lỗ 10/17 → 8/17 ✅ (mục tiêu ≤ 7/17 gần đạt), WR 36.74% → 38.55% (chưa đạt 40% nhưng R:R cải thiện bù đắp)
  - **Success**: WR tổng ≥ 33% ✅, quý lỗ ≤ 7/17 ❌ (8/17)
- [ ] **Tránh BUY cuối phiên** (chỉ live scan) — scan lúc 15:35, nhưng tag signal > 14:45 là "late" và yêu cầu score > 0.65 thay vì 0.55
  - **Rationale**: Late-session rally hay gap down sáng hôm sau.
  - **Success**: Avg gap-down loss giảm (đo qua log live scan Phase 1 sau 30 trades)

### 3.3 Exit Refinement (impact lớn nhất)

- [x] **Trailing stop sau +1R** — khi unrealized gain > 1R (= 1.5×ATR), trail stop tại `high - 2×ATR`; bỏ TP cố định *(commit `e23a2f0`)*
  - **Rationale**: TP hit chỉ 28% (64/227), nhiều winner bị chốt sớm. Trailing cho phép winner chạy trong trend mạnh.
  - **Implementation**: flag `trail_active` trong `Position`/`open_position`; activate khi `high ≥ entry + ATR_TRAIL_TRIGGER × ATR_entry`. Sau đó `stop = max(stop, high - ATR_TRAIL_MULT × ATR_entry)`. Dùng `entry_atr` frozen để đồng nhất khoảng trail trong suốt trade; stop ratchet only up.
  - **Success**: Profit factor ≥ 1.3, CAGR ≥ 5%/năm
  - **Kết quả đo được** (kết hợp với 3.1 + 3.2): PF 1.038 → 1.106 ❌ (mục tiêu 1.3 chưa đạt), CAGR 0.92% → 1.74% ❌ (mục tiêu 5% chưa đạt), nhưng MDD 17.21% → 8.62% ✅ và Sharpe 0.141 → 0.261 (+85%) ✅. Trade-off: avg_win 7.53M → 4.58M (−39%) đổi lấy WR +8.11pp. Đúng hướng kỳ vọng (nhiều winner vừa thay vì ít winner lớn).
- [~] **TP thích nghi theo regime** — cấu trúc code đã implement *(commit `59d79ba`)*, hiện **disabled** do SIDEWAYS 2×ATR cắt quá sớm *(commit `ab0242e`)*.
  - **Rationale**: Sideways cho lại profit nhanh — chốt sớm. Nhiều quý (2023Q3, 2024Q2-Q4) lỗ do thị trường sideways.
  - **Implementation**: `pending_buys` giờ mang thêm `regime`; `Position.take_profit` set tại entry (None khi disabled). Section C kiểm tra `hi >= take_profit` trước trailing ratchet.
  - **Kết quả khi bật**: PF 1.106 → 0.957 ❌ (TRAIL exits −58%, avg_win −26%). Cần tune `TP_SIDEWAYS_MULT ∈ {3.0, 4.0, 4.5}` trước khi bật lại.
  - **Success**: WR trong SIDEWAYS ≥ 35%, PF trong SIDEWAYS > 1.0
- [x] **Breakeven stop sau +1R** — kéo stop về entry khi đạt +1R (bảo vệ chống lỗ) *(commit `96453ce`)*
  - **Rationale**: thay đổi nhỏ, ngăn winning-to-loss flip. 158 stop-out hiện tại có thể giảm đáng kể.
  - **Implementation**: khi trail_active kích hoạt (hi >= entry + 1R), đồng thời set `stop = max(stop, entry_price)`. Áp dụng trong cả `backtest_portfolio_vn30.py` và `core/backtester.py`.
  - **Kết quả đo được** (v1.2): STOP exits 108 → 86 (−21%) ✅, avg_loss −2.41M → −2.64M (tăng nhẹ do sample thay đổi — tổng loss giảm).
  - **Success**: Avg loss giảm 20% — chưa đạt riêng lẻ nhưng STOP count giảm 21% đúng hướng

### 3.4 Position Sizing

- [ ] **Kelly fraction từ 30-trade rolling** — sau 30 trades, dùng `half-Kelly = 0.5 × (W - (1-W)/R)` giới hạn ở 2%
  - **Rationale**: 2% cố định hiện tại không thích nghi với edge quan sát được (đặc biệt trong bear period nên giảm size).
  - **Success**: CAGR ≥ +3%/năm mà MDD không tăng > 2pp
- [ ] **Risk điều chỉnh theo volatility** — regime VOLATILE: giảm `RISK_PCT` xuống 1% (từ 2%)
  - **Rationale**: Volatile = stop dễ bị hit; giảm size bảo vệ vốn.
  - **Success**: MDD ≤ 12%

### 3.5 Portfolio-Level

- [x] **Giới hạn concentration theo sector** — tối đa 2 vị thế mở cùng sector *(commit `6a59e26`)*
  - **Rationale**: VN30 có 6-7 ngân hàng + 4-5 BĐS. Tương quan nội ngành cao → nhiều lúc 5 slot cùng chịu rủi ro tương tự.
  - **Implementation**: `core/sector_map.py` — VN30 sector mapping (BANK, REALESTATE, ENERGY, STEEL, CONSUMER, TECH, FINANCE, AGRI, AIRLINES, CONGLOMERATE). `can_add_to_sector()` kiểm tra trong section B của portfolio backtester (`_MAX_SECTOR_POSITIONS=2`). Unknown sector → permissive.
  - **Kết quả đo được** (v1.2): MDD 8.62% → 7.91% ✅, trades giảm thêm (buộc chọn symbol đa dạng hơn). Daily return std chưa đo riêng.
  - **Success**: MDD ≤ 12% ✅
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
- [x] **Walk-forward re-validation** — script `scripts/backtest_portfolio_walkforward.py` chạy IS/OOS 70/30 trên VN30 portfolio *(commit `2ad3aee`)*
  - **Implementation**: Tách toàn bộ date index 70/30, OOS prepend thêm `_WARMUP=252` bars từ cuối IS để giữ EMA200 calibrated. Chạy full engine v1.2. In IS/OOS comparison table + check Sharpe delta < 0.3.
  - **Success**: IS/OOS Sharpe lệch < 0.3 — chưa chạy với v1.2, cần chạy để validate

### 3.8 Thứ tự ưu tiên (đề xuất)

**Top-3 đã đóng** ✅ — fix bear-period bleed + cải thiện WR. Kết quả: MDD 17.21% → 8.62%, WR 28.63% → 36.74%, Sharpe +85%.

**Round-2 implement xong, v1.2 là baseline mới**: CAGR +3.94%, Sharpe 0.550, MDD 7.91%, PF 1.281, R:R 2.04. Adaptive TP disabled do cắt sớm winners — cần tune trước khi bật lại.

**Vòng tiếp theo: tiếp tục nâng PF và CAGR**:

1. 🔥 **Tune adaptive TP SIDEWAYS** (3.3) — bật lại với `TP_SIDEWAYS_MULT ∈ {3.0, 4.0, 4.5}` để tìm điểm cân bằng win-cut vs chất lượng win. Nếu vẫn tệ hơn → bỏ SIDEWAYS, chỉ giữ VOLATILE=1.5×ATR.
2. 🔥 **Walk-forward validation** (3.7) — chạy `backtest_portfolio_walkforward.py` với v1.2 engine để kiểm tra IS/OOS Sharpe delta < 0.3.
3. **Kelly fraction từ rolling** (3.4) — sau khi PF ổn định, thêm adaptive sizing để scale edge.
4. **Parameter sensitivity grid** (3.7) — sweep `BUY_THRESHOLD ∈ {0.50, 0.55, 0.60}` × `RS_gate ON/OFF` × `sector_limit {2,3}` để tìm robust plateau vs overfit.

---

## 4. Change Log

| Ngày | Thay đổi | Commit | Ghi chú |
|------|----------|--------|---------|
| 2026-04-20 | **Re-baseline v1.2** — adaptive TP disabled | `ab0242e` | CAGR +3.94%, Sharpe 0.550, MDD 7.91%, PF 1.281, R:R 2.04, WR 38.55%, 179 trades. Best result so far. |
| 2026-04-20 | Disable adaptive TP by regime (pending tune) | `ab0242e` | `tp=None` cho tất cả regime; SIDEWAYS 2×ATR cắt quá sớm (TRAIL −58%, PF → 0.957) |
| 2026-04-20 | **Re-baseline v1.1** — Round-2 combined | `228cda5`–`2ad3aee` | WR +6pp (42.73%) ✅ nhưng PF 0.957 ❌, adaptive TP là nguyên nhân chính |
| 2026-04-20 | Walk-forward IS/OOS script (roadmap 3.7) | `2ad3aee` | `scripts/backtest_portfolio_walkforward.py` — 70/30 split với warmup prepend |
| 2026-04-20 | Sector concentration limit max 2/sector (roadmap 3.5) | `6a59e26` | `core/sector_map.py` — 10 sectors VN30. `_MAX_SECTOR_POSITIONS=2` |
| 2026-04-20 | Breakeven stop khi +1R (roadmap 3.3) | `96453ce` | `stop = max(stop, entry_price)` khi trail_active kích hoạt |
| 2026-04-20 | Adaptive TP theo regime (roadmap 3.3) | `59d79ba` | SIDEWAYS: 2×ATR, VOLATILE: 1.5×ATR, TRENDING: trailing only |
| 2026-04-20 | Relative strength vs VN30 basket gate (roadmap 3.1) | `1ddbf43` | `MarketRegime.basket_return_20d()`, hard gate: sym_return_20d ≤ basket → clamp |
| 2026-04-20 | MACD zero-line hard gate (roadmap 3.2) | `228cda5` | Block BUY khi MACD line < 0 |
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
