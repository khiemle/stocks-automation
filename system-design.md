# System Design: VN Auto Trading System

> Phiên bản: 1.0  
> Ngày: 2026-04-17  
> Tham khảo: product-spec.md

---

## 1. Requirements

### 1.1 Functional Requirements

| # | Yêu cầu |
|---|---|
| F1 | Fetch và lưu trữ OHLCV lịch sử 5 năm cho ~300 mã HOSE + HNX |
| F2 | Cập nhật dữ liệu hàng ngày lúc 15:35 sau khi thị trường đóng |
| F3 | Quét toàn bộ ~300 mã, tính composite signal score |
| F4 | Tính position size, stop-loss, take-profit theo ATR + Kelly |
| F5 | Paper trading simulation (Phase 1) |
| F6 | Signal queue với human approval qua web (Phase 2) |
| F7 | Tự động đặt Limit Order qua SSI API lúc 09:10 sáng T+1 |
| F8 | Theo dõi stop/TP mỗi 30 phút trong giờ giao dịch |
| F9 | Circuit breaker tự động dừng khi MDD_real > 150% MDD_backtest |
| F10 | Streamlit dashboard: portfolio, signals, config, reports, backtest |
| F11 | Telegram notifications cho tín hiệu, lệnh khớp, cảnh báo |
| F12 | Walk-forward backtesting với đầy đủ chi phí |

### 1.2 Non-Functional Requirements

| # | Yêu cầu | Mục tiêu |
|---|---|---|
| NF1 | Latency scan toàn bộ 300 mã | < 60 giây |
| NF2 | Uptime trong giờ giao dịch | 99% (local machine) |
| NF3 | Data freshness sau đóng cửa | < 5 phút |
| NF4 | Thời gian đặt lệnh sau approve | < 30 giây |
| NF5 | Storage cho 5 năm × 300 mã | < 500 MB |
| NF6 | Recovery sau crash | < 2 phút (auto restart) |
| NF7 | Audit trail | 100% lệnh được log |
| NF8 | Extensibility — thêm Signal Engine mới | Không sửa bot core, chỉ implement SignalEngineProtocol |
| NF9 | Extensibility — thêm Broker mới | Không sửa bot core, chỉ implement BrokerProtocol |

### 1.3 Constraints

- Chạy trên **1 máy local duy nhất** (không cloud, không distributed)
- Ngôn ngữ: **Python 3.11+**
- Broker hiện tại: **SSI FastConnect API** (có thể mở rộng sang broker khác qua BrokerProtocol)
- Không có short selling trên thị trường cơ sở
- T+2 settlement: không bán trong 2 ngày làm việc sau khi mua
- Biên độ giá: HOSE ±7%, HNX ±10%

---

## 2. High-Level Design

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LOCAL MACHINE                                │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │  Scheduler   │    │  Streamlit   │    │  Telegram Bot        │  │
│  │ (APScheduler)│    │  Web UI      │    │  (Notifications)     │  │
│  └──────┬───────┘    └──────┬───────┘    └──────────────────────┘  │
│         │                   │                        ↑             │
│         ▼                   ▼                        │             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    trading_bot.py (Main Process)            │   │
│  │                                                             │   │
│  │  ┌────────────┐  ┌─────────────┐  ┌────────────────────┐   │   │
│  │  │   Signal   │  │    Risk     │  │  Portfolio Manager  │   │   │
│  │  │   Engine   │  │   Engine    │  │                     │   │   │
│  │  └─────┬──────┘  └──────┬──────┘  └────────┬───────────┘   │   │
│  │        │                │                   │               │   │
│  │        └────────────────┴───────────────────┘               │   │
│  │                         │                                   │   │
│  │  ┌──────────────────────▼──────────────┐                    │   │
│  │  │        Execution Layer              │                    │   │
│  │  │  SimulatedBroker | SSITradingClient │                    │   │
│  │  └──────────────────────┬──────────────┘                    │   │
│  │                         │                                   │   │
│  │  ┌──────────────────────▼──────────────┐                    │   │
│  │  │          Data Manager               │                    │   │
│  │  │     SSIDataClient | DataCache       │                    │   │
│  │  └──────────────────────┬──────────────┘                    │   │
│  └─────────────────────────┼───────────────────────────────────┘   │
│                            │                                        │
│  ┌─────────────────────────▼───────────────────────────────────┐   │
│  │                    Local Storage                             │   │
│  │  ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐  │   │
│  │  │ Parquet Files │  │  SQLite DBs  │  │   JSON Files     │  │   │
│  │  │ (OHLCV 5 năm) │  │ (trades.db) │  │ (portfolio,      │  │   │
│  │  │               │  │             │  │  config,         │  │   │
│  │  │               │  │             │  │  signal_queue)   │  │   │
│  │  └───────────────┘  └──────────────┘  └──────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────┘
                                     │ HTTPS
              ┌──────────────────────┼──────────────────┐
              │                      │                  │
     ┌────────▼───────┐   ┌──────────▼──────┐  ┌───────▼──────┐
     │  SSI FastConnect│   │ SSI FastConnect  │  │  Telegram    │
     │  Data API       │   │ Trading API      │  │  Bot API     │
     │ fc-data.ssi.com │   │fc-tradeapi.ssi.. │  │              │
     └─────────────────┘   └──────────────────┘  └──────────────┘
```

### 2.2 Process Architecture — 2 Processes độc lập

```
Process 1: trading_bot.py          Process 2: streamlit_app.py
─────────────────────────          ──────────────────────────
- Scheduler (APScheduler)          - Web server (port 8501)
- Data fetch & update              - Đọc DB + JSON files
- Signal scanning                  - Viết signal_queue.json
- Risk calculation                 - Viết config.json
- Order execution                  - KHÔNG gọi SSI API trực tiếp
- Portfolio tracking
- Telegram notifications

Giao tiếp qua: shared files (JSON + SQLite)
Không cần IPC, không cần message queue → đơn giản nhất
```

### 2.3 Data Flow

#### Flow 1: Daily Scan (15:35 mỗi ngày)

```
APScheduler trigger (15:35)
        │
        ▼
DataManager.update_daily()
  → Chọn DataSource theo config: SSI hoặc yfinance
  → Chia ~300 mã thành batches (50 mã/batch, delay 2-3s giữa batches)
  → Fetch OHLCV ngày hôm nay cho từng batch    [~30-40 giây tổng]
  → Validate data quality
  → Append vào Parquet files
  → [SSI only] Fetch foreign flow (khối ngoại)
  → [yfinance] foreign_flow = None → weight tín hiệu này = 0
        │
        ▼
MarketScanner.scan()
  → DataManager.get_ohlcv(symbol, 120 ngày) × 300 mã    [parallel, từ cache]
  → SignalEngine.evaluate(symbol)
  → RiskEngine.calculate_position(symbol, score)
  → Filter: score > 0.55 AND vol_MA20 >= 100k
        │
        ▼
signal_queue.json  ←  {status: PENDING, source: "EOD", signals: [...]}
        │
        ▼
TelegramBot.notify("Có N tín hiệu BUY mới, mở web để review")
```

#### Flow 2: Order Execution (09:10 sáng T+1)

```
APScheduler trigger (09:10)
        │
        ▼
Đọc signal_queue.json → lọc status == APPROVED
        │
        ▼
Với mỗi approved signal:
  → Kiểm tra lại: circuit breaker, available slots, T+2
  → SSITradingClient.place_order(LO, symbol, qty, price)
  → Ghi order_id vào signal_queue.json (status: ORDER_PLACED)
  → TelegramBot.notify("Đã đặt lệnh BUY VCB x1,143 @ 87,500")
```

#### Flow 3: Intraday Monitoring — Danh mục + Watchlist (mỗi 30 phút)

```
APScheduler trigger (09:00, 09:30, 10:00, ... 15:00)
        │
        ▼
Gộp danh sách symbols cần fetch:
  portfolio_symbols  = portfolio.json → open positions (≤ 5 mã)
  watchlist_symbols  = config.json → watchlist (≤ 10 mã)
  all_symbols        = portfolio_symbols ∪ watchlist_symbols   (≤ 15 mã)
        │
        ▼
DataSource.get_intraday_price(all_symbols)   [1 batch request duy nhất]
        │
        ├── [DANH MỤC] Với mỗi portfolio position:
        │       → Kiểm tra: current_price <= stop_loss?
        │           → YES: Broker.place_order(SELL) + TelegramBot.notify
        │       → Kiểm tra: current_price >= take_profit?
        │           → YES: Broker.place_order(SELL) + TelegramBot.notify
        │       → Kiểm tra: price tăng > 1R? → update trailing stop
        │       → Ghi lại portfolio.json (updated stops)
        │
        └── [WATCHLIST] Với mỗi watchlist symbol:
                → SignalEngine.evaluate_intraday(symbol, current_price, cached_df)
                  (dùng cached_df từ lần update cuối phiên hôm qua)
                → Nếu score > 0.55:
                    → Thêm vào signal_queue.json (status: PENDING, source: "INTRADAY")
                    → TelegramBot.notify("⚡ Intraday signal: HPG score 0.63")
                → Nếu score <= 0.55: bỏ qua
```

---

## 3. Deep Dive

### 3.1 Data Model

#### SQLite: trades.db

```sql
-- Lịch sử tất cả giao dịch đã đóng
CREATE TABLE trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    exchange        TEXT NOT NULL,           -- HOSE | HNX
    side            TEXT NOT NULL,           -- BUY | SELL
    entry_price     REAL NOT NULL,
    exit_price      REAL,
    shares          INTEGER NOT NULL,
    entry_date      TEXT NOT NULL,           -- ISO 8601
    exit_date       TEXT,
    exit_reason     TEXT,                    -- STOP_LOSS | TAKE_PROFIT | MANUAL | SIGNAL
    pnl             REAL,
    pnl_pct         REAL,
    commission      REAL,
    slippage        REAL,
    signal_score    REAL,
    atr_at_entry    REAL,
    stop_loss       REAL,
    take_profit     REAL,
    mode            TEXT NOT NULL,           -- PAPER | LIVE
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Lịch sử tất cả lệnh đặt (kể cả chưa khớp)
CREATE TABLE orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        TEXT,                    -- SSI order ID
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    order_type      TEXT NOT NULL,           -- LO | ATO
    quantity        INTEGER NOT NULL,
    price           REAL,
    status          TEXT NOT NULL,           -- PENDING|PLACED|FILLED|PARTIAL|CANCELLED|EXPIRED
    signal_price    REAL,                    -- Giá lúc tín hiệu phát sinh
    fill_price      REAL,                    -- Giá thực thi thực tế
    fill_quantity   INTEGER,
    placed_at       TEXT,
    filled_at       TEXT,
    cancelled_at    TEXT,
    mode            TEXT NOT NULL,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Log quét hàng ngày
CREATE TABLE scan_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date       TEXT NOT NULL,
    symbols_scanned INTEGER,
    signals_found   INTEGER,
    signals_approved INTEGER,
    duration_seconds REAL,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Equity history để tính metrics
CREATE TABLE equity_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL UNIQUE,
    total_equity    REAL NOT NULL,
    cash            REAL NOT NULL,
    invested        REAL NOT NULL,
    vnindex_close   REAL,                    -- Benchmark cùng ngày
    mode            TEXT NOT NULL,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
```

#### JSON: portfolio.json

```json
{
  "initial_capital": 500000000,
  "cash": 287500000,
  "week_start_equity": 492000000,
  "backtest_mdd": 0.08,
  "mode": "LIVE",
  "positions": {
    "VCB": {
      "symbol": "VCB",
      "exchange": "HOSE",
      "entry_price": 87500,
      "shares": 1143,
      "stop_loss": 85325,
      "take_profit": 93025,
      "trailing_stop": 85325,
      "atr_at_entry": 1450,
      "entry_date": "2026-04-15T09:22:00",
      "t2_sell_available": "2026-04-17",
      "entry_score": 0.71,
      "ssi_order_id": "ORD20260415001"
    }
  },
  "updated_at": "2026-04-17T10:30:00"
}
```

#### JSON: signal_queue.json

```json
{
  "scan_date": "2026-04-17",
  "scan_time": "15:35:22",
  "signals": [
    {
      "id": "SIG20260417001",
      "symbol": "HPG",
      "exchange": "HOSE",
      "score": 0.72,
      "regime": "TRENDING",
      "signal_price": 24800,
      "suggested_qty": 2016,
      "suggested_stop": 23480,
      "suggested_tp": 28700,
      "atr": 880,
      "rsi": 41,
      "macd_signal": "bullish_crossover",
      "adx": 29,
      "vol_ratio": 1.8,
      "foreign_net_buy": true,
      "status": "PENDING",
      "approved_at": null,
      "order_placed_at": null,
      "expires_at": "2026-04-18T08:30:00"
    }
  ]
}
```

#### JSON: config.json

```json
{
  "capital": {
    "initial": 500000000,
    "max_positions": 5,
    "risk_per_trade_pct": 0.02,
    "max_position_pct": 0.20,
    "cash_buffer_pct": 0.10
  },
  "signal": {
    "min_score": 0.55,
    "min_volume_ma20": 100000,
    "min_adx": 20,
    "min_price": 5000
  },
  "risk": {
    "atr_stop_multiplier": 1.5,
    "atr_tp_multiplier": 4.5,
    "weekly_loss_limit_pct": 0.03,
    "circuit_breaker_mdd_multiplier": 1.5
  },
  "scheduler": {
    "intraday_interval_minutes": 30,
    "daily_scan_time": "15:35",
    "order_placement_time": "09:10",
    "signal_expiry_time": "08:30"
  },
  "mode": {
    "trading": "PAPER",
    "bot_running": false
  },
  "data_source": "YFINANCE",
  "watchlist": ["HPG", "VCB", "VHM"],
  "ssi": {
    "account": "0123456789",
    "data_base_url": "https://fc-data.ssi.com.vn/api/v2/Market",
    "trading_base_url": "https://fc-tradeapi.ssi.com.vn/api/v2"
  }
}

// data_source: "YFINANCE" | "SSI"
// Đổi sang "SSI" sau khi có API key — không cần thay đổi code, chỉ restart bot
// watchlist: tối đa 10 mã, user quản lý qua Streamlit UI
```

#### Parquet: OHLCV data

```
data/market/HOSE/VCB.parquet

Columns:
  date        object    "2024-01-02"
  open        float64   87200.0
  high        float64   88100.0
  low         float64   86800.0
  close       float64   87500.0
  volume      int64     2145300
  adj_close   float64   87500.0   ← điều chỉnh corporate actions

Index: date (string, sorted ascending)
Retention: 5 năm = ~1250 rows/mã
Size/file: ~150KB → 300 mã × 150KB ≈ 45MB total
```

---

### 3.2 API Contracts (Internal)

#### DataSourceProtocol — Interface chung cho SSI và yfinance

```python
from typing import Protocol, List
import pandas as pd

class DataSourceProtocol(Protocol):
    """
    Interface mà cả SSIDataClient và YFinanceClient đều phải implement.
    DataManager inject đúng client theo config["data_source"].
    """

    def get_daily_ohlcv(
        self, symbol: str, from_date: str, to_date: str
    ) -> pd.DataFrame:
        """OHLCV lịch sử — columns: date, open, high, low, close, volume, adj_close"""

    def get_daily_ohlcv_batch(
        self, symbols: List[str], from_date: str, to_date: str
    ) -> dict[str, pd.DataFrame]:
        """Batch download nhiều mã cùng lúc — tối ưu cho daily update"""

    def get_intraday_price(self, symbol: str) -> float:
        """Giá hiện tại (có thể delay ~15 phút với yfinance)"""

    def get_intraday_prices_batch(self, symbols: List[str]) -> dict[str, float]:
        """Batch fetch giá cho danh mục + watchlist (≤ 15 mã)"""

    def get_universe(self, exchange: str = "HOSE") -> List[str]:
        """Danh sách mã theo sàn — SSI tự động, yfinance dùng file tĩnh"""

    def get_foreign_flow(
        self, symbol: str, from_date: str, to_date: str
    ) -> pd.DataFrame | None:
        """Khối ngoại — chỉ SSI hỗ trợ, yfinance trả về None"""
```

---

#### YFinanceClient

```python
import yfinance as yf

class YFinanceClient:
    """
    DataSource dùng yfinance — chạy được ngay không cần API key.
    VN stocks dùng suffix .VN: VCB → VCB.VN, HPG → HPG.VN
    """

    VN_SUFFIX = ".VN"

    def _to_yf_symbol(self, symbol: str) -> str:
        return symbol + self.VN_SUFFIX  # "VCB" → "VCB.VN"

    def get_daily_ohlcv(self, symbol: str, from_date: str, to_date: str) -> pd.DataFrame:
        """Single symbol download"""
        ticker = yf.Ticker(self._to_yf_symbol(symbol))
        df = ticker.history(start=from_date, end=to_date, auto_adjust=True)
        return self._normalize_columns(df)

    def get_daily_ohlcv_batch(
        self, symbols: List[str], from_date: str, to_date: str
    ) -> dict[str, pd.DataFrame]:
        """
        Batch download — hiệu quả hơn nhiều so với từng mã riêng lẻ.
        Dùng cho daily update (50 mã/batch, delay 2s giữa batches).
        """
        yf_symbols = [s + self.VN_SUFFIX for s in symbols]
        raw = yf.download(yf_symbols, start=from_date, end=to_date,
                          auto_adjust=True, group_by="ticker", threads=True)
        result = {}
        for symbol, yf_sym in zip(symbols, yf_symbols):
            if yf_sym in raw.columns.get_level_values(0):
                result[symbol] = self._normalize_columns(raw[yf_sym])
        return result

    def get_intraday_price(self, symbol: str) -> float:
        """Giá gần nhất (~15 phút delay)"""
        ticker = yf.Ticker(self._to_yf_symbol(symbol))
        return ticker.fast_info["last_price"]

    def get_intraday_prices_batch(self, symbols: List[str]) -> dict[str, float]:
        """Batch giá cho ≤ 15 mã — 1 request thay vì N requests"""
        yf_symbols = [s + self.VN_SUFFIX for s in symbols]
        tickers = yf.Tickers(" ".join(yf_symbols))
        return {
            sym: tickers.tickers[yf_sym].fast_info.get("last_price", None)
            for sym, yf_sym in zip(symbols, yf_symbols)
        }

    def get_universe(self, exchange: str = "HOSE") -> List[str]:
        """
        yfinance không có API lấy universe.
        Đọc từ file tĩnh: data/universe/HOSE.txt, HNX.txt
        File này cần cập nhật thủ công khi có mã mới niêm yết.
        """
        path = f"data/universe/{exchange}.txt"
        with open(path) as f:
            return [line.strip() for line in f if line.strip()]

    def get_foreign_flow(self, *args, **kwargs) -> None:
        """yfinance không hỗ trợ khối ngoại — trả về None"""
        return None

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Chuẩn hóa columns về format chung: date, open, high, low, close, volume, adj_close"""
        df = df.rename(columns=str.lower)
        df.index.name = "date"
        df.index = df.index.strftime("%Y-%m-%d")
        return df[["open", "high", "low", "close", "volume"]]
```

---

#### SSIDataClient

```python
class SSIDataClient:
    """
    Wrapper cho SSI FastConnect Data API
    Base URL: https://fc-data.ssi.com.vn/api/v2/Market
    """

    def authenticate(self) -> str:
        """
        POST /AccessToken
        Input:  { consumerID, consumerSecret }
        Output: JWT access token (cached, auto-refresh)
        Raises: SSIAuthError nếu credentials sai
        """

    def get_daily_ohlcv(
        self,
        symbol: str,
        from_date: str,    # "YYYY-MM-DD"
        to_date: str,      # "YYYY-MM-DD"
        page_size: int = 100
    ) -> pd.DataFrame:
        """
        GET /DailyOhlc?symbol=VCB&fromDate=2024-01-01&toDate=2026-04-17
        Output: DataFrame[date, open, high, low, close, volume]
        Raises: SSIDataError | SSIRateLimitError
        """

    def get_intraday_price(self, symbol: str) -> float:
        """
        GET /IntradayOhlc?symbol=VCB&pageIndex=1&pageSize=1
        Output: float — giá giao dịch gần nhất
        Dùng trong giờ giao dịch để check stop/TP
        """

    def get_universe(self, exchange: str = "HOSE") -> List[str]:
        """
        GET /Securities?exchange=HOSE&pageSize=500
        Output: ["VCB", "VHM", "HPG", ...]
        """

    def get_foreign_flow(
        self, symbol: str, from_date: str, to_date: str
    ) -> pd.DataFrame:
        """
        GET /ForeignRoom?symbol=VCB&...
        Output: DataFrame[date, buy_volume, sell_volume, net_value]
        """
```

#### SSITradingClient

```python
class SSITradingClient:
    """
    Wrapper cho SSI FastConnect Trading API
    Base URL: https://fc-tradeapi.ssi.com.vn/api/v2
    """

    def place_order(
        self,
        symbol: str,
        side: str,          # "B" | "S"
        quantity: int,
        order_type: str,    # "LO" (chỉ dùng LO)
        price: float,
        account: str
    ) -> OrderResult:
        """
        POST /Order/NewOrder
        Output: OrderResult(order_id, status, message)
        Raises: SSIOrderError | SSIInsufficientFundsError
        """

    def cancel_order(self, order_id: str, account: str) -> bool:
        """
        POST /Order/CancelOrder
        Output: True nếu hủy thành công
        """

    def get_order_status(self, order_id: str) -> OrderStatus:
        """
        GET /Order/OrderStatus?orderId=...
        Output: OrderStatus(id, status, filled_qty, fill_price)
        """

    def get_account_balance(self, account: str) -> AccountBalance:
        """
        GET /Portfolio/AccountBalance?account=...
        Output: AccountBalance(cash, buying_power, nav)
        """

    def get_stock_positions(self, account: str) -> List[StockPosition]:
        """
        GET /Portfolio/StockPosition?account=...
        Output: [StockPosition(symbol, qty, avg_price, market_value)]
        Dùng để reconcile với portfolio.json
        """
```

---

### 3.3 Scheduler Design

```python
# APScheduler — tất cả jobs trong 1 process

scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")

# 1. Intraday monitoring — chỉ chạy trong giờ giao dịch
scheduler.add_job(
    func=monitor_positions,
    trigger="cron",
    day_of_week="mon-fri",
    hour="9-11,13-15",
    minute="0,30",
    id="intraday_monitor"
)

# 2. Daily scan sau đóng cửa
scheduler.add_job(
    func=daily_scan,
    trigger="cron",
    day_of_week="mon-fri",
    hour=15, minute=35,
    id="daily_scan"
)

# 3. Đặt lệnh sáng T+1
scheduler.add_job(
    func=place_approved_orders,
    trigger="cron",
    day_of_week="mon-fri",
    hour=9, minute=10,
    id="order_placement"
)

# 4. Hủy lệnh chưa khớp cuối ngày
scheduler.add_job(
    func=cancel_unfilled_orders,
    trigger="cron",
    day_of_week="mon-fri",
    hour=14, minute=30,
    id="cancel_unfilled"
)

# 5. Cập nhật equity history
scheduler.add_job(
    func=record_daily_equity,
    trigger="cron",
    day_of_week="mon-fri",
    hour=15, minute=10,
    id="equity_snapshot"
)

# 6. Reset weekly P&L (thứ 2 đầu tuần)
scheduler.add_job(
    func=reset_weekly_pnl,
    trigger="cron",
    day_of_week="mon",
    hour=8, minute=0,
    id="weekly_reset"
)

# 7. Expire stale signals
scheduler.add_job(
    func=expire_old_signals,
    trigger="cron",
    day_of_week="mon-fri",
    hour=8, minute=30,
    id="expire_signals"
)
```

---

### 3.4 Parallel Scan Design

Quét 300 mã trong < 60 giây cần xử lý song song:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def scan_all_symbols(universe: List[str]) -> List[ScanResult]:
    results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit tất cả jobs
        futures = {
            executor.submit(scan_single_symbol, symbol): symbol
            for symbol in universe
            if symbol not in open_positions
        }

        # Collect results
        for future in as_completed(futures, timeout=60):
            symbol = futures[future]
            try:
                result = future.result()
                if result and result.score >= MIN_SCORE:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Scan failed for {symbol}: {e}")
                # Không raise — 1 mã lỗi không dừng toàn bộ scan

    return sorted(results, key=lambda x: x.score, reverse=True)

def scan_single_symbol(symbol: str) -> ScanResult | None:
    df = data_manager.get_ohlcv(symbol, days=120)  # Từ Parquet cache
    if df is None or len(df) < 60:
        return None
    signal = signal_engine.evaluate(df)
    if signal.score < MIN_SCORE:
        return None
    position = risk_engine.calculate(symbol, signal, portfolio)
    return ScanResult(symbol=symbol, signal=signal, position=position)
```

**Ước tính thời gian:**
- 300 mã ÷ 10 workers = 30 batches
- Mỗi mã: đọc Parquet (~5ms) + tính indicators (~10ms) = ~15ms
- 30 batches × 15ms = ~450ms tổng cộng
- Thêm overhead + data fetch = **< 30 giây** ✅

---

### 3.5 Error Handling

```
┌─────────────────────────────────────────────────────────────┐
│                   ERROR CATEGORIES                          │
├──────────────────┬──────────────────────────────────────────┤
│ SSI API errors   │ → Retry 3 lần với exponential backoff    │
│ (timeout, 5xx)   │   Nếu vẫn lỗi → log + skip lần scan này  │
│                  │   KHÔNG crash toàn bộ bot                 │
├──────────────────┼──────────────────────────────────────────┤
│ Auth expired     │ → Auto refresh token + retry request      │
│ (401)            │                                           │
├──────────────────┼──────────────────────────────────────────┤
│ Order rejected   │ → Log chi tiết (giá, khối lượng, lý do)  │
│ bởi SSI          │   Telegram alert + update signal status   │
│                  │   KHÔNG retry order tự động               │
├──────────────────┼──────────────────────────────────────────┤
│ Data missing     │ → Skip mã đó trong scan lần này          │
│ (symbol lỗi)     │   Log vào errors.log                      │
├──────────────────┼──────────────────────────────────────────┤
│ Circuit breaker  │ → Dừng TẤT CẢ new positions              │
│ triggered        │   Hủy tất cả PENDING orders              │
│                  │   Telegram alert khẩn cấp                 │
│                  │   Yêu cầu manual restart                  │
├──────────────────┼──────────────────────────────────────────┤
│ Process crash    │ → Auto restart bởi watchdog script        │
│                  │   State được recover từ portfolio.json    │
│                  │   Log đầy đủ trước khi crash              │
└──────────────────┴──────────────────────────────────────────┘
```

**Watchdog script:**
```bash
# watchdog.sh — chạy trong tmux/screen
while true; do
    python trading_bot.py start
    echo "Bot crashed at $(date), restarting in 30s..."
    sleep 30
done
```

---

### 3.6 State Recovery sau crash

```python
def recover_state():
    """Chạy khi bot khởi động — reconcile state với SSI"""

    # 1. Load portfolio từ file
    portfolio = PortfolioManager.load()

    # 2. Reconcile với SSI thực tế
    ssi_positions = ssi_trading.get_stock_positions(ACCOUNT)
    reconcile_positions(portfolio.positions, ssi_positions)
    # → Log diff nếu có chênh lệch
    # → Alert nếu diff > 0

    # 3. Check pending orders từ hôm qua
    pending_signals = load_signal_queue(status="ORDER_PLACED")
    for signal in pending_signals:
        status = ssi_trading.get_order_status(signal.order_id)
        update_signal_status(signal.id, status)

    # 4. Resume scheduler bình thường
```

---

### 3.7 Extensibility — Plugin Architecture

Hệ thống được thiết kế mở để có thể thêm Signal Engine và Execution Engine mới mà **không thay đổi core bot logic**. Nguyên tắc: bot chỉ giao tiếp với interface, không biết implementation cụ thể.

---

#### 3.7.1 SignalEngineProtocol — Pluggable Signal Strategies

```python
from typing import Protocol
import pandas as pd
from dataclasses import dataclass

@dataclass
class SignalResult:
    score: float           # -1.0 → +1.0
    regime: str            # "TRENDING" | "VOLATILE" | "SIDEWAYS"
    action: str            # "BUY" | "SELL" | "HOLD"
    indicators: dict       # Raw indicator values (for UI display)
    confidence: float      # 0.0 → 1.0 (dùng để scale position size)

class SignalEngineProtocol(Protocol):
    """
    Interface mà mọi Signal Engine đều phải implement.
    Bot chỉ gọi evaluate() — không quan tâm bên trong tính gì.
    """
    name: str              # e.g. "MomentumV1", "MeanReversionV1"
    version: str           # e.g. "1.0.0"

    def evaluate(
        self,
        df: pd.DataFrame,                      # OHLCV 120 ngày gần nhất
        foreign_flow: pd.DataFrame | None      # None nếu dùng yfinance
    ) -> SignalResult:
        """Chạy sau 15:35 — dùng OHLCV đầy đủ của ngày"""

    def evaluate_intraday(
        self,
        df: pd.DataFrame,                      # OHLCV cache từ hôm qua
        current_price: float                   # Giá real-time / delayed
    ) -> SignalResult:
        """Chạy mỗi 30 phút — dùng cho watchlist monitoring"""
```

**Các engine đã có và dự kiến:**

| Engine | Mô tả | Status |
|---|---|---|
| `MomentumV1` | MA20/60 + MACD + RSI + ADX + Volume + Khối ngoại | 🟡 Phase 1 |
| `MeanReversionV1` | RSI oversold + Bollinger Band + volume spike | 🔵 Tương lai |
| `VolatilityBreakoutV1` | ATR expansion + volume breakout sau consolidation | 🔵 Tương lai |
| `SectorRotationV1` | So sánh momentum theo ngành | 🔵 Tương lai |

**Đăng ký engine trong config:**

```json
"signal_engines": [
    { "name": "MomentumV1", "enabled": true, "weight": 1.0 }
]
```

> Khi có nhiều engine, MarketScanner tổng hợp kết quả (weighted average score) hoặc chạy độc lập theo từng watchlist riêng.

---

#### 3.7.2 BrokerProtocol — Pluggable Execution Engines

```python
from typing import Protocol, List
from dataclasses import dataclass

@dataclass
class OrderResult:
    order_id: str
    status: str            # "PLACED" | "REJECTED" | "SIMULATED"
    message: str

@dataclass
class OrderStatus:
    order_id: str
    status: str            # "PENDING" | "FILLED" | "PARTIAL" | "CANCELLED"
    filled_qty: int
    fill_price: float | None

@dataclass
class AccountBalance:
    cash: float
    buying_power: float
    nav: float             # Net Asset Value

@dataclass
class StockPosition:
    symbol: str
    qty: int
    avg_price: float
    market_value: float

class BrokerProtocol(Protocol):
    """
    Interface mà mọi Execution Engine đều phải implement.
    Bot không biết đang giao dịch thật hay giả lập.
    """
    name: str              # e.g. "SimulatedBroker", "SSIBroker"

    def place_order(
        self,
        symbol: str,
        side: str,          # "B" | "S"
        quantity: int,
        order_type: str,    # "LO" | "ATO"
        price: float | None,
        account: str
    ) -> OrderResult: ...

    def cancel_order(self, order_id: str, account: str) -> bool: ...

    def get_order_status(self, order_id: str) -> OrderStatus: ...

    def get_account_balance(self, account: str) -> AccountBalance: ...

    def get_stock_positions(self, account: str) -> List[StockPosition]: ...
```

**Các broker đã có và dự kiến:**

| Broker | Mô tả | Status |
|---|---|---|
| `SimulatedBroker` | Fill tại T+1 open, tính đủ phí — dùng cho paper trading & backtest | 🟡 Phase 1 |
| `SSIBroker` | SSI FastConnect Trading API — live trading | 🔵 Phase 2 |
| `BSCBroker` | BSC Securities API — nếu muốn đổi CTCK | 🔵 Tương lai |
| `VPSBroker` | VPS Securities API | 🔵 Tương lai |

**Chọn broker trong config:**

```json
"broker": "SimulatedBroker"
```

> Đổi từ `SimulatedBroker` sang `SSIBroker` là bước chuyển từ Phase 1 → Phase 2. Toàn bộ bot logic giữ nguyên.

---

#### 3.7.3 Cách bot inject dependencies

```python
# trading_bot.py — wiring tại startup

def build_bot(config: dict) -> TradingBot:
    # Data source
    data_source = {
        "YFINANCE": YFinanceClient,
        "SSI":      SSIDataClient,
    }[config["data_source"]]()

    # Signal engine(s)
    engines = [
        ENGINE_REGISTRY[e["name"]]()
        for e in config["signal_engines"]
        if e["enabled"]
    ]

    # Broker (execution engine)
    broker = {
        "SimulatedBroker": SimulatedBroker,
        "SSIBroker":       SSIBroker,
    }[config["broker"]]()

    return TradingBot(
        data_source=data_source,
        signal_engines=engines,
        broker=broker,
    )
```

**Kết quả:** Toàn bộ switch giữa paper/live, SSI/yfinance, Momentum/MeanReversion đều chỉ là **thay đổi config.json** — không sửa code bot.

---

## 4. Storage Design

### 4.1 Tại sao dùng Parquet cho OHLCV?

| | Parquet | SQLite | CSV |
|---|---|---|---|
| Read speed (120 ngày) | **~5ms** | ~20ms | ~50ms |
| Write (append 1 ngày) | Rewrite file (~10ms) | INSERT (~1ms) | Append (~1ms) |
| Storage (300 mã × 5 năm) | **~45MB** | ~150MB | ~200MB |
| Query linh hoạt | Cần pandas | SQL | Cần parse |
| Phù hợp time-series | ✅ | ⚠️ | ❌ |

**Kết luận:** Parquet tối ưu cho đọc time-series (scan 300 mã) — là operation thực hiện nhiều nhất.

### 4.2 Tại sao dùng SQLite cho trades?

- Cần query linh hoạt (filter by date, symbol, mode)
- Cần ACID transactions khi ghi lệnh
- Dễ export CSV, dễ inspect bằng tools
- Không cần multiple writers → SQLite đủ dùng

### 4.3 Tại sao dùng JSON cho portfolio/config/signals?

- portfolio.json: ghi thường xuyên, cần human-readable, size nhỏ
- config.json: Streamlit web ghi, bot đọc — JSON là format tự nhiên
- signal_queue.json: short-lived data (1 ngày), không cần DB

---

## 5. Scale & Reliability

### 5.1 Load Estimation

| Operation | Tần suất | Thời gian | Ghi chú |
|---|---|---|---|
| Daily scan (300 mã) | 1 lần/ngày | ~30 giây | Từ Parquet cache |
| Intraday price check | ~16 lần/ngày × N positions | ~1-2 giây | Chỉ mã đang giữ |
| Order placement | ~2-5 lần/ngày | < 5 giây | Sáng T+1 |
| SSI API calls/ngày | ~50-100 calls | — | Trong giới hạn |
| Storage growth/năm | ~10MB | — | 300 mã × 252 ngày |

### 5.2 Bottleneck Analysis

```
Bottleneck 1: Daily scan 300 mã
  → Giải quyết: ThreadPoolExecutor(max_workers=10)
  → Đọc từ local Parquet (không gọi API)

Bottleneck 2: SSI API rate limit
  → Intraday chỉ fetch mã đang nắm giữ (tối đa 5 mã)
  → Daily fetch: batch theo thời gian, không cùng lúc

Bottleneck 3: Streamlit web reload
  → Streamlit auto-refresh theo interval
  → Đọc từ file cache → không gọi SSI API
```

### 5.3 Failover

```
Trường hợp 1: SSI Data API không phản hồi lúc 15:35
  → Retry 3 lần (1s, 2s, 4s)
  → Nếu vẫn fail: dùng dữ liệu hôm qua + cảnh báo Telegram
  → Không scan BUY mới, chỉ quản lý vị thế hiện có

Trường hợp 2: SSI Trading API không phản hồi lúc 09:10
  → Retry 3 lần
  → Nếu vẫn fail: KHÔNG đặt lệnh, alert Telegram
  → User có thể đặt thủ công qua iBoard

Trường hợp 3: Máy tính tắt/ngủ trong giờ giao dịch
  → Watchdog không thể restart nếu máy tắt
  → Rủi ro: stop-loss không được kiểm tra
  → Giải pháp Phase 3: đặt stop-loss trực tiếp lên sàn (contingency order)
    thay vì chỉ check phần mềm

Trường hợp 4: Network mất kết nối
  → Retry với exponential backoff
  → Log + Telegram alert khi network phục hồi
```

---

## 6. Trade-off Analysis

### 6.1 Local Machine vs Cloud

| | Local Machine (hiện tại) | Cloud Server |
|---|---|---|
| Chi phí | ✅ $0 | ❌ ~$10-30/tháng |
| Uptime | ⚠️ Phụ thuộc máy tính bật | ✅ 99.9% |
| Setup | ✅ Đơn giản | ❌ Phức tạp hơn |
| Security | ✅ Private, không lộ credentials | ⚠️ Cần bảo mật tốt |
| Risk khi mất điện | ⚠️ Bot dừng, không check stop | ✅ Không ảnh hưởng |

**Quyết định:** Local machine cho Phase 1+2. Xem xét chuyển cloud khi Phase 3 với 500M VND — uptime quan trọng hơn.

### 6.2 JSON files vs SQLite cho signal_queue

| | JSON | SQLite |
|---|---|---|
| Đọc/ghi bởi Streamlit | ✅ Dễ | ⚠️ Cần connection |
| Concurrent access | ⚠️ Race condition nếu đọc/ghi cùng lúc | ✅ ACID |
| Human-readable | ✅ | ❌ |
| Phù hợp signal queue (short-lived) | ✅ | Overkill |

**Quyết định:** JSON cho signal_queue. Race condition không nghiêm trọng vì bot và web không ghi cùng lúc vào cùng 1 field.

### 6.3 Parallel Workers: 10 vs nhiều hơn

| max_workers | Thời gian scan | CPU load | SSI API risk |
|---|---|---|---|
| 5 | ~60 giây | Thấp | Thấp |
| **10** | **~30 giây** | **Vừa** | **Vừa** |
| 20 | ~15 giây | Cao | Rate limit risk |
| 50 | ~8 giây | Rất cao | Bị block |

**Quyết định:** max_workers=10. Đọc từ local Parquet nên không lo rate limit SSI. Chỉ cần hoàn thành trước 16:00.

### 6.4 Streamlit vs FastAPI + React

| | Streamlit | FastAPI + React |
|---|---|---|
| Time to build | ✅ 1-2 tuần | ❌ 4-6 tuần |
| Performance | ⚠️ Rerun toàn bộ khi có action | ✅ Reactive |
| Customization | ⚠️ Giới hạn | ✅ Thoải mái |
| Phù hợp với 1 user | ✅ | Overkill |
| Real-time updates | ⚠️ Cần polling | ✅ WebSocket |

**Quyết định:** Streamlit cho Phase 1+2. Nếu Phase 3 cần real-time push notifications hoặc nhiều user → xem xét FastAPI + React.

---

## 7. Điều sẽ cần revisit khi scale

| Khi nào | Vấn đề | Giải pháp |
|---|---|---|
| Phase 3 (500M VND) | Uptime critical hơn | Chuyển sang VPS/cloud |
| Nhiều chiến lược | Signal conflicts, capital allocation | Multi-strategy framework |
| Vốn > 5 tỷ | Market impact khi đặt lệnh lớn | VWAP/TWAP execution |
| Muốn real-time web | Streamlit polling chậm | FastAPI + React + WebSocket |
| Mở rộng sang phái sinh | Hoàn toàn khác biệt | Tách riêng thành module mới |

---

## 8. Implementation Order

Theo thứ tự dependency — build từ dưới lên:

```
Week 1-2:  SSIDataClient + DataManager + Parquet storage
           → Test: fetch 5 năm data cho 300 mã

Week 3:    SignalEngine + RiskEngine
           → Test: scan 1 mã, verify signals không có look-ahead

Week 4:    PortfolioManager + SQLite schema
           → Test: mở/đóng vị thế paper, tính P&L

Week 5:    Backtester (SimulatedBroker + walk-forward)
           → Test: backtest HPG 3 năm, verify metrics

Week 6:    Scheduler + BotCycle (daily scan + intraday monitor)
           → Test: paper trading 2 tuần liên tục

Week 7:    Streamlit Web (4 trang cơ bản)
           → Test: dashboard + signal queue UI

Week 8:    Telegram Bot + Error handling
           → Test: end-to-end paper trading simulation

Phase 2:   SSITradingClient + order placement
           (Sau khi đăng ký SSI API và paper trading 60 ngày)
```
