# Product Spec: Hệ thống Auto Trading Cổ phiếu Việt Nam

> Phiên bản: 1.0  
> Ngày: 2026-04-17  
> Tác giả: Khiem  
> Tham khảo: algotrade-foundation.md, algotrade-02-strategies.md, algotrade-03-data-testing.md, algotrade-04-evaluation-operations.md, algotrade-05-practice-lab.md

---

## 1. Product Vision

Xây dựng hệ thống swing trading **bán tự động → tự động hoàn toàn**, chạy trên máy local, kết nối SSI iBoard API, quét toàn bộ cổ phiếu HOSE + HNX mỗi ngày sau giờ đóng cửa, đưa ra tín hiệu mua/bán dựa trên kỹ thuật, quản lý vị thế với risk control chặt chẽ, và cung cấp web dashboard để theo dõi và quản lý toàn bộ quy trình.

### Tham số cố định

| Tham số | Giá trị |
|---|---|
| Broker | SSI iBoard API |
| Thị trường | HOSE + HNX (cổ phiếu cơ sở) |
| Phong cách | Swing trading 3-10 ngày |
| Vốn kiểm thử (Phase 2) | 50,000,000 VND |
| Vốn production (Phase 3) | 500,000,000 VND |
| Mục tiêu lợi nhuận | 15-20%/năm |
| Theo dõi | 1-2 lần/ngày |
| Môi trường chạy | Local machine (Linux/macOS/Windows) |
| Web UI | Streamlit |

### Kỳ vọng thực tế

- 15-20%/năm với 500M VND = 75-100M lợi nhuận
- Win rate ~52-55% với R:R tối thiểu 1:2 là đủ để đạt mục tiêu
- Cần tối thiểu **300 giao dịch** để kết quả có ý nghĩa thống kê (Algotrade Bài 43)
- Không cần thuật toán phức tạp — kỷ luật và risk management quan trọng hơn

---

## 2. Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA LAYER                               │
│   DataSourceProtocol ← SSIDataClient | YFinanceClient       │
│   Local Cache: Parquet (OHLCV) + SQLite (trades)           │
│   Historical DB (5 năm) + Daily Update 15:35 (batch fetch) │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│            SIGNAL ENGINE (Pluggable)                        │
│   SignalEngineProtocol ← MomentumV1 | MeanReversionV1 | …  │
│   Quét ~300 mã sau 15:35 + Watchlist mỗi 30 phút           │
│   → SignalResult: score, regime, action, indicators        │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                  RISK ENGINE                                │
│   ATR-based position sizing (2% risk/trade)                │
│   Stop-loss (ATR × 1.5) + Take-profit (ATR × 4.5)         │
│   T+2 enforcement + Price band check (HOSE/HNX)            │
│   Circuit breaker: MDD_real > 150% MDD_backtest → STOP     │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│            EXECUTION LAYER (Pluggable)                      │
│   BrokerProtocol ← SimulatedBroker | SSIBroker | …         │
│   Phase 1: SimulatedBroker (paper trading)                 │
│   Phase 2: SSIBroker — Web approve → SSI API đặt lệnh      │
│   Phase 3: SSIBroker — Tự động hoàn toàn                   │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│               PORTFOLIO MANAGER                             │
│   SQLite: trades.db + portfolio state                       │
│   Metrics: Sharpe, Sortino, Information Ratio, MDD         │
│   So sánh benchmark: VN-Index                              │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│            BACKTESTING ENGINE                               │
│   Walk-forward validation (70% train / 30% test)           │
│   SimulatedBroker: fill tại giá mở cửa T+1                 │
│   Chi phí đầy đủ: 0.15%/chiều + slippage 0.1%             │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│         STREAMLIT WEB DASHBOARD                              │
│   Dashboard · Signal Queue + Watchlist · Config · Reports   │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Cấu trúc thư mục

```
stocks-assistant/
├── streamlit_app.py            # Web UI entry point
├── trading_bot.py              # Bot chính — chạy độc lập, chứa build_bot()
├── core/
│   ├── __init__.py
│   ├── protocols.py            # DataSourceProtocol, SignalEngineProtocol, BrokerProtocol + dataclasses
│   ├── risk_engine.py          # Position sizing + stops (ATR-based)
│   ├── portfolio_manager.py    # Quản lý vốn + vị thế + metrics
│   ├── market_scanner.py       # Quét toàn bộ HOSE+HNX (parallel)
│   ├── backtester.py           # Walk-forward backtesting
│   └── data_manager.py         # Parquet cache + daily update + validate
├── signals/
│   ├── __init__.py
│   ├── registry.py             # ENGINE_REGISTRY — đăng ký các SignalEngine theo tên
│   └── momentum_v1.py          # MomentumV1: MA20/60 + MACD + RSI + ADX + Volume + Khối ngoại
├── brokers/
│   ├── __init__.py
│   ├── simulated_broker.py     # SimulatedBroker — paper trading & backtest
│   └── ssi_broker.py           # SSIBroker — SSI FastConnect Trading API (Phase 2)
├── data_sources/
│   ├── __init__.py
│   ├── yfinance_client.py      # YFinanceClient — không cần API key
│   └── ssi_data_client.py      # SSIDataClient — SSI FastConnect Data API
├── integrations/
│   └── telegram_bot.py         # Telegram notifications
├── data/
│   ├── market/
│   │   ├── HOSE/               # {SYMBOL}.parquet — OHLCV lịch sử
│   │   ├── HNX/
│   │   └── index/
│   │       └── VNINDEX.parquet
│   ├── universe/
│   │   ├── HOSE.txt            # Danh sách mã HOSE (dùng cho yfinance)
│   │   └── HNX.txt             # Danh sách mã HNX
│   ├── corporate_actions/
│   │   └── dividends.csv       # Điều chỉnh giá sau cổ tức/phát hành
│   └── foreign_flow/
│       └── khoi_ngoai.parquet  # Net buy/sell khối ngoại hàng ngày (SSI only)
├── db/
│   └── trades.db               # SQLite — lịch sử giao dịch (paper + live)
├── config/
│   ├── config.json             # Tham số hệ thống (có thể sửa qua web)
│   └── .env                    # SSI API keys (không commit git)
├── state/
│   ├── portfolio.json          # Trạng thái danh mục hiện tại
│   └── signal_queue.json       # Tín hiệu PENDING/APPROVED/REJECTED
└── algotrade*.md               # Knowledge base (tham khảo)
```

---

## 4. Layer Chi Tiết

---

### Layer 1: DATA LAYER

**Mục tiêu:** Cung cấp dữ liệu sạch, đầy đủ cho Signal Engine và Backtester với độ trễ thấp nhất.

#### 4.1.1 Nguồn dữ liệu

| Nguồn | Vai trò | Khi nào dùng |
|---|---|---|
| SSI FastConnect Data API | OHLCV lịch sử + Daily update + Intraday + Khối ngoại | Khi đã có API key (Phase 2+) |
| yfinance | OHLCV lịch sử + Daily update (VN stocks với suffix `.VN`) | Phase 1 (chưa có SSI key) hoặc fallback |
| FireAnt / Fialda | Backup khẩn cấp | Khi cả SSI + yfinance đều lỗi |
| VN-Index | Benchmark | SSI hoặc yfinance (`^VNINDEX`) |

> Tham khảo Bài 30: API luôn là nguồn nhanh nhất. SSI là mục tiêu dài hạn; yfinance đủ dùng cho Phase 1 paper trading.

**Giới hạn của yfinance (cần biết):**
- OHLCV lịch sử: ✅ Đầy đủ, hỗ trợ batch download nhiều mã cùng lúc
- Daily update: ✅ Có (~15-30 phút delay sau đóng cửa — chấp nhận được cho 15:35 scan)
- Intraday giá real-time: ⚠️ Delay ~15 phút (dùng được để check stop/TP trong phiên)
- Khối ngoại (foreign flow): ❌ Không có → tắt signal này khi dùng yfinance (weight = 0)
- Universe list: ⚠️ Cần tự duy trì danh sách mã (không có API lấy tự động như SSI)

#### 4.1.1b DataSource Abstraction — Switchable giữa SSI và yfinance

Cả hai data source implement cùng 1 interface, `DataManager` chọn source theo config:

```python
class DataSourceProtocol(Protocol):
    def get_daily_ohlcv(self, symbol: str, from_date: str, to_date: str) -> pd.DataFrame: ...
    def get_intraday_price(self, symbol: str) -> float: ...
    def get_universe(self, exchange: str) -> List[str]: ...
    def get_foreign_flow(self, symbol: str, from_date: str, to_date: str) -> pd.DataFrame | None: ...

# config.json: "data_source": "YFINANCE" | "SSI"
# DataManager tự inject đúng client theo config
```

**Khi switch từ yfinance → SSI (sau khi có API key):**
- Data Parquet đã có sẵn → không cần re-download lịch sử
- Chỉ cần đổi `data_source` trong config.json → restart bot
- Foreign flow signal tự động enable lại

#### 4.1.2 Historical Data Management

**Chiến lược lưu trữ:**

```
OHLCV data → Parquet files (nhanh, nhỏ, efficient với pandas)
  - Mỗi mã 1 file: data/market/HOSE/HPG.parquet
  - Columns: date, open, high, low, close, volume, adj_close
  - Retention: 5 năm (đủ cho backtesting có ý nghĩa thống kê)

Corporate actions → CSV
  - Ghi nhận: ngày cổ tức, tỷ lệ, ngày GDKHQ
  - Dùng để tính adj_close chính xác

Foreign flow → Parquet
  - Net buy/sell khối ngoại hàng ngày trên VN30 stocks
  - Columns: date, symbol, buy_volume, sell_volume, net_value
```

**Lần đầu khởi tạo (Initial Load):**

```bash
python trading_bot.py init-data --years 5
# 1. Fetch toàn bộ HOSE+HNX từ yfinance (5 năm)
# 2. Điều chỉnh split/dividend
# 3. Validate data quality
# 4. Lưu vào Parquet files
# Ước tính: ~300 mã × 5 năm = ~300MB storage
```

**Cập nhật hàng ngày (Daily Update — 15:35 sau đóng cửa):**

```bash
# Chạy tự động lúc 15:35 sau khi thị trường đóng cửa (15:05-15:15)
python trading_bot.py update-data

# Chiến lược fetch để tránh rate limit:
# 1. Chia ~300 mã thành batches (50 mã/batch)
# 2. Mỗi batch cách nhau 2-3 giây
# 3. Tổng thời gian: ~30-45 giây → xong trước 15:36

# Nếu data_source = YFINANCE:
#   yf.download(batch_of_50_symbols, period="5d", auto_adjust=True)
#   → batch download nhanh hơn nhiều so với từng mã riêng lẻ

# Nếu data_source = SSI:
#   SSIDataClient.get_daily_ohlcv(symbol, today, today) × từng mã
#   → có retry logic riêng cho từng mã

# Sau khi fetch xong:
# 1. Validate data quality (Bài 27)
# 2. Append vào Parquet files
# 3. Fetch foreign flow (SSI only — skip nếu dùng yfinance)
# 4. Log kết quả vào scan.log
```

**Phân bổ request để tránh rate limit:**

```
15:35:00 — Batch 1: mã 001-050   (50 mã, ~3-5 giây fetch)
15:35:05 — Batch 2: mã 051-100   (delay 2-3 giây giữa batches)
15:35:10 — Batch 3: mã 101-150
...
15:35:30 — Batch 6: mã 251-300
15:35:35 — Validate + write Parquet
15:35:45 — Signal scan bắt đầu
```

**Data Quality Rules (Bài 27):**

- Giá ngoài biên độ ±7% HOSE / ±10% HNX trong 1 phiên → flag bất thường
- Volume = 0 trong ngày giao dịch → flag thiếu dữ liệu
- Gap giá > 15% giữa 2 phiên liên tiếp → kiểm tra corporate actions
- Tự động fill missing dates bằng cách forward-fill hoặc bỏ qua

**Data Access API (internal):**

```python
class DataManager:
    def get_ohlcv(self, symbol: str, days: int = 120) -> pd.DataFrame:
        """Trả về N ngày gần nhất từ Parquet cache"""

    def get_universe(self, exchange: str = "ALL") -> List[str]:
        """Trả về danh sách mã HOSE + HNX"""

    def get_foreign_flow(self, symbol: str, days: int = 20) -> pd.DataFrame:
        """Trả về net buy/sell khối ngoại"""

    def get_vnindex(self, days: int = 252) -> pd.DataFrame:
        """Trả về VN-Index làm benchmark"""

    def update_daily(self) -> UpdateReport:
        """Cập nhật dữ liệu cuối ngày từ SSI API"""

    def validate_data(self, symbol: str) -> ValidationReport:
        """Kiểm tra chất lượng dữ liệu 1 mã"""
```

---

### Layer 2: SIGNAL ENGINE (Pluggable)

**Mục tiêu:** Quét ~300 mã sau 15:35, cho điểm từng mã, trả về danh sách candidates có tín hiệu BUY mạnh. Kiến trúc mở để thêm nhiều chiến lược khác nhau mà không thay đổi bot core.

**Interface:** Mọi Signal Engine đều implement `SignalEngineProtocol` (định nghĩa trong `core/protocols.py`). Bot chỉ gọi `evaluate()` và `evaluate_intraday()`.

**Engine hiện tại: `MomentumV1`** (`signals/momentum_v1.py`)

#### 4.2.1 Chiến lược: Momentum (Bài 10)

Lý do chọn Momentum thay vì Mean Reversion:
- Thị trường VN có tính momentum rõ trong pha tăng/giảm mạnh
- Không có short selling → chỉ cần tín hiệu long → đơn giản hơn
- Swing 3-10 ngày phù hợp với time horizon của Momentum

#### 4.2.2 Bộ tín hiệu composite

| Chỉ báo | Vai trò | Weight | Nguồn |
|---|---|---|---|
| MA crossover (20/60) | Xác nhận xu hướng chính | 0.25 | Bài 10 |
| MACD | Timing entry, momentum | 0.25 | Bài 10 |
| RSI(14) | Tránh overbought entry | 0.20 | Bài 10-11 |
| ADX(14) > 25 | Lọc thị trường đi ngang | 0.15 | Bài 34 |
| Volume ratio (vol/MA20) | Xác nhận lực mua | 0.10 | Bài 26 |
| Khối ngoại net buy | Tín hiệu xác nhận thêm | 0.05 | Bài 58 |

**Regime detection:**

```python
if ADX > 25:
    regime = "TRENDING"   # Giữ nguyên weights
elif ATR/close > 3%:
    regime = "VOLATILE"   # Giảm confidence × 0.7
else:
    regime = "SIDEWAYS"   # MA weight × 0.7, giảm Momentum signals
```

**Ngưỡng kết quả:**

```
score > 0.55  → BUY signal (chặt hơn để giảm false positives)
score < -0.55 → SELL signal (exit existing position)
còn lại       → HOLD
```

#### 4.2.3 Bộ lọc loại trừ

- Volume MA20 < 100,000 cổ/ngày → loại (thanh khoản quá thấp)
- Giá < 5,000 VND → loại (penny stocks)
- Mã đã có trong danh mục → loại khỏi BUY candidates
- Cổ phiếu trong giai đoạn đình chỉ giao dịch → loại

#### 4.2.4 Tránh overfitting (Bài 35)

- Giữ số lượng tham số ít — không tối ưu quá nhiều biến
- Dùng "luật biến thiên theo regime" thay vì tham số cố định
- Validate trên out-of-sample data trước khi deploy

---

### Layer 3: RISK ENGINE

**Mục tiêu:** Tính toán position size an toàn và thiết lập các mức stop/target dựa trên volatility thực tế.

#### 4.3.1 Position Sizing — Kelly Criterion (Bài 45)

Sau khi có đủ 300 trades thực tế, tính Kelly:

```
f = (p × b - q) / b
  p = win rate (từ lịch sử giao dịch)
  b = average win / average loss (R:R ratio)
  q = 1 - p

Áp dụng: Half-Kelly (f × 0.5) để bảo thủ hơn
```

**Giai đoạn đầu (chưa đủ 300 trades):**

```
capital_at_risk  = available_cash × 0.02          # 2% vốn/lệnh
stop_distance    = ATR(14) × 1.5
shares           = floor(capital_at_risk / stop_distance)
max_position     = total_equity × 0.20             # Tối đa 20%/mã
```

#### 4.3.2 Stop-loss và Take-profit

```
stop_loss   = entry_price - ATR(14) × 1.5
take_profit = entry_price + ATR(14) × 4.5    # R:R = 1:3

Trailing stop: kích hoạt khi giá tăng > 1R
  → stop_loss mới = current_price - ATR(14) × 1.5
```

#### 4.3.3 Circuit Breaker — Quy tắc 150% MDD (Bài 44)

> Đây là safety net quan trọng nhất khi chuyển từ paper sang live

```python
# Dừng toàn bộ hệ thống nếu:
if real_MDD > backtest_MDD * 1.5:
    stop_all_new_positions()
    send_alert("⚠️ CIRCUIT BREAKER: MDD thực vượt ngưỡng 150%")
    # Chờ review thủ công trước khi restart
```

Ngoài ra:
- Dừng thêm vị thế mới nếu P&L tuần < -3%
- Cảnh báo nếu P&L tuần < -1.5%

#### 4.3.4 Đặc thù thị trường Việt Nam

```
T+2 enforcement:
  - Lưu entry_date cho mỗi vị thế
  - Không tạo SELL order trong vòng 2 ngày làm việc sau entry_date

Price band check:
  - HOSE: stop_loss không thấp hơn giá sàn ngày (close × 0.93)
  - HNX: stop_loss không thấp hơn giá sàn ngày (close × 0.90)
  - Nếu stop quá gần giá sàn → cảnh báo, không entry

Volume filter:
  - Chỉ mua nếu vol_MA20 >= 100,000 cổ/ngày
  - Kích thước lệnh <= 5% average daily volume (tránh market impact)
```

---

### Layer 4: BACKTESTING ENGINE

**Mục tiêu:** Validate chiến lược trước khi đụng tiền thật, phát hiện overfitting, đo lường hiệu quả theo chuẩn Algotrade Hub.

#### 4.4.1 Kiến trúc "Giả lập CTCK" (Bài 33)

> Cùng 1 đoạn code signal/risk chạy được cả 3 môi trường: backtest, paper trading, live — nhờ `BrokerProtocol`

```python
class SimulatedBroker:
    """
    Implement BrokerProtocol — giả lập CTCK cho paper trading & backtest.
    Phase 2 chỉ cần swap sang SSIBroker, toàn bộ bot logic giữ nguyên.
    """
    def place_order(self, symbol, side, quantity, order_type, price, account) -> OrderResult
    def cancel_order(self, order_id, account) -> bool
    def get_order_status(self, order_id) -> OrderStatus
    def get_account_balance(self, account) -> AccountBalance
    def get_stock_positions(self, account) -> List[StockPosition]
```

**Fill logic:**

```
BUY order → fill tại giá MỞ CỬA của bar tiếp theo (T+1)
            (tránh look-ahead bias — Bài 32)

SELL order → fill tại giá MỞ CỬA bar tiếp theo
             + enforce T+2 settlement

Slippage → 0.1% trên giá fill
Commission → 0.15% trên giá trị lệnh mỗi chiều
```

#### 4.4.2 Walk-forward Validation (Bài 36)

```
Toàn bộ data (5 năm)
├── In-sample (70%): 3.5 năm — dùng để optimize tham số
└── Out-of-sample (30%): 1.5 năm — validate kết quả

Nếu Out-of-sample performance < 70% In-sample performance:
→ Khả năng cao overfitting → đơn giản hóa chiến lược
```

#### 4.4.3 Metrics báo cáo bắt buộc (Bài 33 + 43-45)

| Metric | Mục tiêu | Nguồn |
|---|---|---|
| Tổng lợi nhuận | > 15%/năm | Bài 43 |
| Sharpe Ratio | > 1.0 | Bài 43, 34 |
| Sortino Ratio | > 1.2 | Bài 04 |
| Information Ratio vs VN-Index | > 0 | Bài 04 |
| Maximum Drawdown | < 15% | Bài 44 |
| Win Rate | > 52% | Bài 43 |
| Profit Factor | > 1.5 | Bài 33 |
| Chuỗi thua dài nhất | < 8 lệnh | Bài 33 |
| Số giao dịch | >= 300 | Bài 43 |

> **Quan trọng:** Tối ưu hóa Sharpe Ratio — không phải lợi nhuận tuyệt đối (Bài 43)

#### 4.4.4 CLI commands

```bash
# Backtest 1 mã
python trading_bot.py backtest HPG --years 3

# Backtest toàn bộ chiến lược
python trading_bot.py backtest-all --years 3

# Walk-forward report
python trading_bot.py backtest-all --walk-forward --split 0.7
```

---

### Layer 5: EXECUTION LAYER

**Mục tiêu:** Thực thi lệnh chính xác, an toàn, đo lường chi phí thực tế.

#### 4.5.1 SSI FastConnect API — Custom HTTP Client

**Quyết định:** Tự viết HTTP client dựa trên SSI official API specs — không dùng thư viện bên thứ ba (`ssi-fctrading`, `ssi-fc-data`). Lý do: kiểm soát hoàn toàn error handling, retry logic, timeout; không phụ thuộc thư viện có thể ngừng maintain.

**Tham khảo:** [SSI FastConnect API Docs](https://guide.ssi.com.vn/ssi-products/fastconnect-data/api-specs)

---

**Credentials cần có:**

```
CONSUMER_ID       # Đăng ký tại iboard.ssi.com.vn
CONSUMER_SECRET
PRIVATE_KEY       # Dùng cho Trading API (ký lệnh)
ACCOUNT           # Số tài khoản SSI
```

**Đăng ký:** Ra chi nhánh SSI mang CCCD → iboard.ssi.com.vn → Dịch vụ hỗ trợ → Dịch vụ API → Tạo khóa kết nối mới → lưu CONSUMER_ID, CONSUMER_SECRET, PRIVATE_KEY

---

**Kiến trúc 2 client riêng biệt:**

```
integrations/
├── ssi_data_client.py      # FastConnect Data — lấy giá, OHLCV lịch sử
└── ssi_trading_client.py   # FastConnect Trading — đặt/hủy lệnh
```

---

**SSI FastConnect Data Client:**

```
Base URL:  https://fc-data.ssi.com.vn/
Auth URL:  https://fc-data.ssi.com.vn/api/v2/Market/AccessToken

Bước 1 — Lấy access token:
  POST /api/v2/Market/AccessToken
  Body: { "consumerID": "...", "consumerSecret": "..." }
  Response: { "accessToken": "<JWT>", "message": "Success" }

Bước 2 — Gọi API với Bearer token:
  Header: Authorization: Bearer <accessToken>

Token management:
  - JWT có thời hạn → tự động refresh khi expired
  - Cache token trong memory, không gọi auth mỗi request
```

**Endpoints cần dùng:**

| Endpoint | Mục đích | Tần suất |
|---|---|---|
| `GET /api/v2/Market/DailyOhlc` | OHLCV ngày lịch sử | Daily update 15:35 |
| `GET /api/v2/Market/IntradayOhlc` | OHLCV intraday | Theo dõi vị thế (30 phút) |
| `GET /api/v2/Market/Securities` | Danh sách mã HOSE/HNX | Khởi tạo universe |
| `GET /api/v2/Market/IndexComponents` | Thành phần VN30, VN-Index | Benchmark |
| `GET /api/v2/Market/ForeignRoom` | Dữ liệu khối ngoại | Signal thêm |

```python
class SSIDataClient:
    BASE_URL = "https://fc-data.ssi.com.vn/api/v2/Market"

    def __init__(self, consumer_id: str, consumer_secret: str):
        self._consumer_id = consumer_id
        self._consumer_secret = consumer_secret
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    def _get_token(self) -> str:
        """Lấy token, tự refresh nếu hết hạn"""

    def _get(self, endpoint: str, params: dict) -> dict:
        """GET request với auth header + retry 3 lần nếu lỗi"""

    def get_daily_ohlcv(self, symbol: str, from_date: str, to_date: str) -> pd.DataFrame:
        """OHLCV daily lịch sử — dùng khi initial load và daily update"""

    def get_intraday_price(self, symbol: str) -> float:
        """Giá real-time — dùng trong giờ giao dịch để check stop/TP"""

    def get_universe(self, exchange: str) -> List[str]:
        """Danh sách mã theo sàn: HOSE | HNX"""

    def get_foreign_flow(self, symbol: str, days: int) -> pd.DataFrame:
        """Net buy/sell khối ngoại"""
```

---

**SSI FastConnect Trading Client:**

```
Base URL:   https://fc-tradeapi.ssi.com.vn/
Stream URL: wss://fc-tradehub.ssi.com.vn/

Auth: tương tự Data API nhưng dùng thêm PRIVATE_KEY để ký lệnh
```

**Endpoints cần dùng:**

| Endpoint | Mục đích |
|---|---|
| `POST /api/v2/Order/NewOrder` | Đặt lệnh mua/bán |
| `POST /api/v2/Order/CancelOrder` | Hủy lệnh |
| `GET /api/v2/Order/OrderStatus` | Trạng thái lệnh |
| `GET /api/v2/Portfolio/AccountBalance` | Số dư tài khoản |
| `GET /api/v2/Portfolio/StockPosition` | Vị thế cổ phiếu đang giữ |

```python
class SSITradingClient:
    BASE_URL = "https://fc-tradeapi.ssi.com.vn/api/v2"

    def place_order(self,
        symbol: str,
        side: str,          # "B" = Buy | "S" = Sell
        quantity: int,
        order_type: str,    # "LO" | "ATO" | "ATC"
        price: float | None = None,
        account: str = ""
    ) -> OrderResult:
        """Đặt lệnh — chỉ dùng LO cho swing trading"""

    def cancel_order(self, order_id: str, account: str) -> bool:
        """Hủy lệnh chưa khớp"""

    def get_order_status(self, order_id: str) -> OrderStatus:
        """Kiểm tra lệnh đã khớp chưa"""

    def get_account_balance(self) -> AccountBalance:
        """Số dư tiền mặt + sức mua"""

    def get_positions(self) -> List[StockPosition]:
        """Danh sách cổ phiếu đang nắm giữ từ SSI"""
```

---

**Error handling & Retry logic (bắt buộc):**

```python
# Áp dụng cho mọi HTTP request
def _request_with_retry(self, method, url, **kwargs):
    for attempt in range(3):
        try:
            response = requests.request(method, url, timeout=10, **kwargs)
            if response.status_code == 401:
                self._refresh_token()   # Token hết hạn → refresh
                continue
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            if attempt == 2: raise
            time.sleep(2 ** attempt)    # Exponential backoff: 1s, 2s, 4s
        except requests.ConnectionError:
            if attempt == 2: raise
            time.sleep(2 ** attempt)
```

#### 4.5.2 Lịch chạy hàng ngày

**Câu hỏi quan trọng:** Tín hiệu 15:30 dùng data ngày nào?

> Scan chạy lúc 15:35 — sau khi thị trường đóng cửa (15:00-15:05). Lúc này OHLCV hôm nay đã **hoàn chỉnh**. Signal dựa trên giá đóng cửa **hôm nay**, lệnh đặt **sáng hôm sau**.

```
Thị trường đóng: 15:05
      ↓
15:35  [BOT] Fetch OHLCV hôm nay (đầy đủ) cho ~300 mã
             → Tính Signal Engine → tìm BUY candidates
             → Ghi signal_queue.json
             → Thông báo Telegram + cập nhật web

16:00  [USER] Mở web, review tín hiệu, bấm APPROVE/REJECT

09:10  [BOT] Đặt Limit Order cho tín hiệu đã approve
sáng          (giá tham chiếu hôm qua ± 0.5%)
T+1
      ↓
09:15+ [SSI] Thị trường mở → lệnh khớp
```

**Trong giờ giao dịch — theo dõi danh mục + watchlist:**

```
09:00 - 11:30 }
13:00 - 15:05 }  Mỗi 30 phút:

  [DANH MỤC — tối đa 5 mã]
    → Fetch giá hiện tại cho CÁC MÃ ĐANG NẮM GIỮ
    → Kiểm tra stop-loss hit → tạo SELL order ngay
    → Kiểm tra take-profit hit → tạo SELL order ngay
    → Update trailing stop nếu giá tăng > 1R

  [WATCHLIST — tối đa 10 mã do user tự thêm]
    → Fetch giá hiện tại cho CÁC MÃ TRONG WATCHLIST
    → Chạy SignalEngine.evaluate() nhanh (giá hiện tại + cache indicators)
    → Nếu score > 0.55 → thêm vào signal_queue với status PENDING
    → Thông báo Telegram: "⚡ Intraday signal: HPG score 0.63"
    → User có thể APPROVE trên web để đặt lệnh ngay hoặc chờ cuối phiên

  Tổng số request mỗi 30 phút: tối đa 15 mã (5 portfolio + 10 watchlist)
  → Không ảnh hưởng rate limit
```

**Watchlist — quản lý:**
- User thêm/xóa mã qua Streamlit (Trang 2: Signal Queue)
- Tối đa 10 mã trong watchlist
- Watchlist được lưu trong `config.json` → persist qua các phiên
- Intraday signal từ watchlist có label `source: "INTRADAY"` để phân biệt với signal cuối phiên

**Tóm tắt logic dữ liệu:**

| Thời điểm | Dữ liệu dùng | Mục đích |
|---|---|---|
| Trong ngày (mỗi 30 phút) | Giá hiện tại: danh mục (≤5) + watchlist (≤10) | Quản lý stop/TP + cơ hội intraday |
| 15:35 | OHLCV đầy đủ của ~300 mã (batch 50/lần) | Tìm BUY signal cuối phiên |
| 09:10 sáng T+1 | Giá tham chiếu từ tín hiệu đã approve | Đặt Limit Order |

#### 4.5.3 Order Types

```
Swing trading → dùng Limit Order (LO)
  - Kiểm soát giá vào tốt hơn
  - Đặt tại giá đóng cửa hôm qua ± 0.5% (ngưỡng chấp nhận được)
  - Không dùng ATO/ATC (không kiểm soát được giá)
  - Nếu không khớp trong ngày T+1 → hủy lệnh, chờ tín hiệu tiếp theo

Phiên đặt lệnh: sáng ngày T+1 lúc 09:10 (trước khi thị trường mở)
Hủy lệnh tự động: 14:30 nếu chưa khớp
```

#### 4.5.4 Implementation Shortfall Tracking (Bài 42)

```python
# Ghi lại cho mỗi lệnh:
{
    "signal_price":    87500,    # Giá khi tín hiệu phát sinh (15:30 T)
    "decision_price":  87500,    # Giá khi user approve
    "order_price":     87800,    # Giá limit order đặt
    "fill_price":      87900,    # Giá thực thi thực tế
    "delay_cost":      400,      # fill_price - signal_price
    "fill_ratio":      0.95,     # Khớp 95% khối lượng dự kiến
}
```

#### 4.5.5 Phase 2: Signal Queue (Semi-auto)

```
[Ngày T — 15:35]
  Signal Engine quét 300 mã → signal_queue.json (status: PENDING)
       ↓
[Ngày T — 15:35 đến 21:00]
  Streamlit Web hiển thị tín hiệu + chart + indicators
  User bấm APPROVE → status: APPROVED
  User bấm REJECT  → status: REJECTED
       ↓
[Ngày T+1 — 09:10]
  Bot đọc signal_queue.json → lấy các APPROVED signals
  → Gọi SSI API đặt Limit Order
  → Cập nhật status: ORDER_PLACED
       ↓
[Ngày T+1 — trong ngày]
  Theo dõi kết quả khớp lệnh
  → Khớp: status: FILLED → mở vị thế mới
  → Không khớp đến 14:30: status: EXPIRED → hủy lệnh

Lưu ý: Nếu user không approve trước 08:30 sáng T+1 → tín hiệu tự động EXPIRED
```

---

### Layer 6: PORTFOLIO MANAGER

**Mục tiêu:** Theo dõi trạng thái danh mục, tính toán P&L chính xác, persist state qua các phiên chạy.

#### 4.6.1 Data Model

```python
@dataclass
class Position:
    symbol: str
    entry_price: float
    shares: int
    stop_loss: float
    take_profit: float
    atr_at_entry: float
    entry_date: datetime
    entry_score: float
    t2_sell_available: date       # Ngày có thể bán (T+2)

@dataclass
class Trade:
    symbol: str
    entry_price: float
    exit_price: float
    shares: int
    entry_date: datetime
    exit_date: datetime
    exit_reason: str              # STOP_LOSS | TAKE_PROFIT | MANUAL | SIGNAL
    pnl: float
    pnl_pct: float
    commission: float
    slippage: float

@dataclass
class PortfolioState:
    initial_capital: float
    cash: float
    positions: Dict[str, Position]
    trades: List[Trade]
    week_start_equity: float
    backtest_mdd: float           # Dùng cho circuit breaker
    created_at: datetime
```

#### 4.6.2 Tính năng kế toán (Bài 46)

```python
class PortfolioManager:
    def total_equity(self, current_prices: Dict[str, float]) -> float
    def realized_pnl(self) -> float
    def unrealized_pnl(self, current_prices: Dict[str, float]) -> float
    def weekly_pnl_pct(self, current_equity: float) -> float
    def current_mdd(self) -> float
    def information_ratio(self, vnindex_returns: List[float]) -> float
    def sharpe_ratio(self, risk_free_rate: float = 0.045) -> float
    def sortino_ratio(self) -> float
    def win_rate(self) -> float
    def profit_factor(self) -> float
```

---

### Layer 7: STREAMLIT WEB DASHBOARD

**Mục tiêu:** Giao diện duy nhất để theo dõi, quản lý tín hiệu, cấu hình, và phân tích hiệu quả.

#### 4.7.1 Trang 1: Dashboard tổng quan

```
Header:
  Tổng vốn | Tiền mặt | Invested | P&L hôm nay | P&L tuần | P&L YTD

Portfolio Status:
  Vị thế hiện tại (N/5)
  Circuit breaker status: ✅ OK | ⚠️ WARNING | 🛑 STOPPED
  MDD thực tế vs MDD backtest (progress bar)

Active Positions Table:
  Symbol | Entry Price | Current Price | P&L% | Stop | TP | Days held | T+2 date

Charts:
  Equity curve vs VN-Index (line chart)
  P&L by month (bar chart)
```

#### 4.7.2 Trang 2: Signal Queue (Phase 2 — quan trọng nhất)

```
Scan thực hiện lúc: 15:32:10 | Số mã quét: 287 | Tín hiệu BUY: 4

Signal Card (mỗi tín hiệu):
  🟢 BUY  VCB  |  Score: 0.71  |  Regime: TRENDING
  Giá vào: 87,500  Stop: 82,300  TP: 103,400  (R:R 1:3)
  Khối lượng: 1,143 cổ (~100M VND = 20% portfolio)
  RSI: 38 | MA20/60: ↑ crossover | MACD: bullish | ADX: 28
  Khối ngoại: Net buy 3 ngày liên tiếp (+2.3B)
  [✅ APPROVE]  [❌ REJECT]  [👁 Chart]

Approved signals sẽ được đặt lệnh lúc: 09:10 sáng mai (T+1)
```

#### 4.7.3 Trang 3: Cấu hình hệ thống

```
Bot Control:
  [▶ Start Bot]  [⏸ Pause]  [⏹ Stop]
  Mode: [ ] Paper  [x] Live
  Polling interval: [30] phút

Data Source:
  Source: ( ) yfinance  (•) SSI FastConnect
  ⚠️  Đổi data source sẽ restart bot ở lần scan tiếp theo
  [Trạng thái kết nối SSI: ✅ OK | ❌ Không kết nối được]

Capital Settings:
  Initial capital: [500,000,000] VND
  Max positions: [5]
  Risk per trade: [2] %
  Max position size: [20] %

Signal Settings:
  Min score threshold: [0.55]
  Min volume MA20: [100,000] cổ/ngày
  Min ADX: [20]

Risk Settings:
  ATR stop multiplier: [1.5]
  ATR TP multiplier: [4.5]
  Weekly loss limit: [3] %
  Circuit breaker MDD multiplier: [1.5]

[💾 Save Config]  [↩ Reset to Default]
```

> **Lưu ý Data Source:** Khi chọn yfinance, signal Khối ngoại tự động bị tắt (weight = 0). Khi switch sang SSI, Khối ngoại được enable lại. Lịch sử Parquet không bị ảnh hưởng khi switch.

#### 4.7.4 Trang 4: Báo cáo & Phân tích

```
Khoảng thời gian: [Last 30 days] [Last 3 months] [YTD] [All time]

Performance Summary:
  Total Return | Sharpe Ratio | Sortino Ratio | Information Ratio
  Max Drawdown | Win Rate | Profit Factor | Total Trades

Charts:
  Monthly returns heatmap
  Win/loss distribution
  MDD chart theo thời gian
  Rolling Sharpe (30 ngày)

Trade Log:
  Date | Symbol | Entry | Exit | P&L | P&L% | Reason | Days held
  [Export CSV]

Benchmark Comparison:
  Portfolio vs VN-Index (cumulative return chart)
```

#### 4.7.5 Trang 5: Backtesting

```
Chọn chiến lược và khoảng thời gian → chạy backtest → xem kết quả

Settings:
  Symbols: [All HOSE+HNX] hoặc [VN30 only] hoặc chọn tay
  Period: [2021] - [2026]
  Walk-forward: [x] Enable (split 70/30)

[▶ Run Backtest]

Results:
  In-sample vs Out-of-sample performance
  Equity curve
  Monthly returns table
  Full metrics report
  Trade list
```

#### 4.7.6 Kiến trúc Streamlit — tách biệt với Bot

```python
# streamlit_app.py chỉ:
#   1. ĐỌC từ: trades.db, portfolio.json, signal_queue.json
#   2. VIẾT vào: config.json, signal_queue.json (approve/reject)
#   3. KHÔNG chạy bot, không gọi SSI API trực tiếp

# trading_bot.py chạy độc lập:
#   1. Đọc config.json
#   2. Đọc signal_queue.json (approved signals) → đặt lệnh
#   3. Viết portfolio.json, trades.db, signal_queue.json (new signals)
```

---

### Layer 8: MONITORING & NOTIFICATIONS

**Mục tiêu:** Thông báo kịp thời khi có tín hiệu, lỗi, hoặc circuit breaker kích hoạt.

#### 4.8.1 Telegram Bot

```
Thông báo tự động:
  - Có tín hiệu BUY/SELL mới sau 15:30
  - Lệnh được khớp thành công
  - Stop-loss/Take-profit bị hit
  - Circuit breaker kích hoạt
  - Bot bị lỗi hoặc crash
  - Báo cáo tóm tắt hàng ngày lúc 16:00

Format ví dụ:
  🟢 BUY Signal — VCB
  Score: 0.71 | Giá: 87,500
  → Mở web để approve
  http://localhost:8501
```

#### 4.8.2 Logging

```
logs/
├── bot.log        # Toàn bộ hoạt động bot
├── trades.log     # Mỗi lệnh đặt + kết quả khớp
├── errors.log     # Lỗi API, lỗi hệ thống
└── scan.log       # Kết quả quét hàng ngày
```

---

## 5. Tech Stack

| Thành phần | Công nghệ | Lý do |
|---|---|---|
| Ngôn ngữ | Python 3.11+ | Tiêu chuẩn cho algo trading (Bài 56) |
| Web UI | Streamlit | Tích hợp Python, không cần frontend riêng |
| Data storage | SQLite + Parquet | SQLite cho trades, Parquet cho time-series |
| Data processing | pandas, numpy | Standard cho tài chính |
| Technical analysis | pandas-ta hoặc ta-lib | Tính toán MACD, RSI, ADX... |
| Scheduler | APScheduler | Chạy scan lúc 15:30 hàng ngày |
| Data source | `yfinance` (Phase 1) / SSI FastConnect Data API (Phase 2+) | Switchable qua config, không sửa code |
| SSI Data API | `requests` + custom HTTP client | `SSIDataClient` — tự viết, không dùng thư viện bên thứ ba |
| SSI Trading API | `requests` + custom HTTP client | `SSIBroker` — tự viết, implement BrokerProtocol |
| Telegram | python-telegram-bot | Notifications |
| Charts | Plotly | Interactive charts trong Streamlit |
| Config | python-dotenv + JSON | Quản lý credentials và tham số |

---

## 6. Roadmap — 3 Phases

---

### Phase 1: Paper Trading *(Mục tiêu: 2 tháng)*

**Mục tiêu:** Validate chiến lược trên dữ liệu thật, không có tiền thật.

**Cần build:**

- [ ] `core/protocols.py` — `DataSourceProtocol`, `SignalEngineProtocol`, `BrokerProtocol` + dataclasses
- [ ] `data_sources/yfinance_client.py` — `YFinanceClient` (primary cho Phase 1)
- [ ] `data_sources/ssi_data_client.py` — `SSIDataClient` (khi có API key)
- [ ] `core/data_manager.py` — Parquet cache, batch daily update, validate
- [ ] `signals/momentum_v1.py` — `MomentumV1` implement `SignalEngineProtocol`
- [ ] `signals/registry.py` — `ENGINE_REGISTRY`
- [ ] `core/risk_engine.py` — ATR position sizing, stop/TP, circuit breaker
- [ ] `brokers/simulated_broker.py` — `SimulatedBroker` implement `BrokerProtocol`
- [ ] `core/backtester.py` — walk-forward validation
- [ ] `core/portfolio_manager.py` — paper portfolio tracking + metrics
- [ ] `trading_bot.py` — `build_bot()` + APScheduler + daily scan lúc 15:35
- [ ] `streamlit_app.py` — Dashboard + Signal Queue + Watchlist + Config + Reports + Backtest
- [ ] Telegram bot — thông báo tín hiệu hàng ngày

**Milestone để chuyển Phase 2:**

| Tiêu chí | Ngưỡng |
|---|---|
| Thời gian paper trading | >= 60 ngày |
| Sharpe Ratio | >= 1.0 |
| Information Ratio vs VN-Index | >= 0 (không thua thị trường) |
| MDD trong paper trading | <= 15% |
| Win rate | >= 52% |
| Số giao dịch | >= 30 (chưa đủ 300 nhưng đủ để đánh giá sơ bộ) |
| Bug nghiêm trọng | 0 |

---

### Phase 2: Semi-Auto với SSI API *(Mục tiêu: 2 tháng)*

**Mục tiêu:** Giao dịch thật với 50M VND, user vẫn confirm trước khi lệnh được đặt.

**Cần build thêm:**

- [ ] `brokers/ssi_broker.py` — `SSIBroker` implement `BrokerProtocol` (SSI FastConnect Trading API)
- [ ] Đổi config `broker: "SSIBroker"` + `data_source: "SSI"` — không sửa bot logic
- [ ] Implementation shortfall tracking (signal_price → order_price → fill_price)
- [ ] T+2 enforcement thực tế với SSI account
- [ ] Real portfolio reconciliation: so sánh `portfolio.json` với `SSIBroker.get_stock_positions()`

**Quan trọng trước khi bắt đầu Phase 2:**

1. Đăng ký SSI iBoard API tại iboard.ssi.com.vn
2. Lưu CONSUMER_ID, CONSUMER_SECRET, PRIVATE_KEY vào `.env`
3. Test API với tài khoản thật nhưng lệnh nhỏ (1 cổ phiếu)
4. Set `initial_capital = 50_000_000` trong config

**Milestone để chuyển Phase 3:**

| Tiêu chí | Ngưỡng |
|---|---|
| Thời gian live trading | >= 60 ngày |
| Lợi nhuận thực tế | >= 0% (không lỗ vốn) |
| MDD thực < 150% MDD backtest | Bắt buộc |
| Không có lỗi API hoặc lỗi lệnh | Bắt buộc |
| Số giao dịch tích lũy | >= 60 |

---

### Phase 3: Full Auto *(Ongoing)*

**Mục tiêu:** Hệ thống tự chạy, scale lên 500M VND.

**Cần build thêm:**

- [ ] Bỏ human confirmation loop
- [ ] Tự động đặt lệnh sáng T+1 lúc 09:10
- [ ] Enhanced circuit breakers với auto-pause
- [ ] Auto restart nếu process crash
- [ ] Kelly Criterion position sizing (đã có đủ data)
- [ ] Báo cáo tuần/tháng tự động qua Telegram
- [ ] Quy trình cải tiến: chạy phiên bản beta song song (Bài 59)

**Điều kiện scale vốn từ 50M → 500M:**

- Tổng số giao dịch >= 300 (Bài 43)
- Kết quả Phase 2 đạt cả 5 milestone
- MDD_real < 150% MDD_backtest trong toàn Phase 2

---

## 7. Các Quy tắc Không Được Vi phạm

Được rút ra trực tiếp từ Algotrade Knowledge Hub:

1. **300 trades rule (Bài 43):** Không kết luận chiến lược thành công hay thất bại khi chưa có 300 giao dịch
2. **MDD 150% rule (Bài 44):** Tự động dừng khi MDD thực vượt 150% MDD backtest — không có ngoại lệ
3. **Optimize Sharpe, không optimize lợi nhuận (Bài 43):** Hai thứ này khác nhau và hay bị nhầm
4. **Fill tại giá T+1 open (Bài 32):** Không fill tại giá thấp nhất của nến — đây là look-ahead bias
5. **Tính đủ chi phí (Bài 32):** 0.15%/chiều + slippage 0.1% — thiếu phí = backtest ảo
6. **Paper trading 2 tháng (Bài 38):** Không skip — đây là bước phát hiện overfitting
7. **Half-Kelly (Bài 45):** Dùng 50% công thức Kelly — Kelly đầy đủ quá rủi ro trong thực tế
8. **Không bao giờ all-in (Bài 45):** Kelly chứng minh toán học: tối đa 20% vốn/lệnh

---

## 8. Câu hỏi cần giải quyết trước khi code

| Câu hỏi | Mức độ ưu tiên |
|---|---|
| SSI API có cung cấp dữ liệu lịch sử OHLCV không? | 🔴 Critical |
| Đã có tài khoản SSI và đăng ký iBoard API chưa? | 🔴 Critical |
| SSI API có cung cấp dữ liệu khối ngoại không? | 🟡 Medium |
| Dùng thư viện SSI chính thức hay tự viết HTTP client? | 🟡 Medium |
| Deploy trên Windows hay Linux/macOS? | 🟡 Medium |
| Cần Telegram notifications ngay từ Phase 1 không? | 🟢 Low |
