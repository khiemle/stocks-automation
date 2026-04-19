# VN Auto Trading System

Swing-trading bot cho thị trường chứng khoán Việt Nam (HOSE + HNX).  
3 phases: Paper Trading → Semi-auto (SSI API) → Full auto.

> **Nguồn chính thống cho thuật toán**: [`docs/vn-swing-trading.md`](docs/vn-swing-trading.md) — algo spec hiện tại, baseline metrics, và roadmap cải tiến. Mọi thay đổi signal/risk/execution phải cập nhật file này theo protocol ở section 5.

## Yêu cầu

```bash
Python 3.11+
pip install -r requirements.txt
```

## Cấu trúc thư mục

```
trading_bot.py          # Bot chính (APScheduler, CLI)
streamlit_app.py        # Web dashboard (port 8501)
core/                   # DataManager, RiskEngine, PortfolioManager,
                        # Backtester, MarketRegime (VN30 macro filter)
signals/                # MomentumV1 + ENGINE_REGISTRY
brokers/                # SimulatedBroker, SSIBroker
data_sources/           # YFinanceClient, SSIDataClient
integrations/           # Telegram bot
scripts/                # backtest_portfolio_vn30.py (portfolio baseline),
                        # backtest_vn30.py (per-symbol diagnostic)
docs/                   # vn-swing-trading.md (algorithm SSoT)
data/universe/          # HOSE.txt, HNX.txt (~290 mã)
tests/unit/             # Unit tests
tests/integration/      # Integration tests
tests/e2e/              # End-to-end tests
```

## Trạng thái hiện tại (2026-04-19)

- **Milestones 1-4** đã hoàn thành (Data Layer, Signal & Risk Engine, Portfolio Manager, Backtester).
- **Baseline VN30 portfolio (500M, max 5 slots, 4 năm)** — sau khi đóng Top-3 roadmap items (macro filter, volume gate, trailing stop): CAGR +1.74%, Sharpe 0.261, MDD 8.62%, WR 36.74%, PF 1.106. Xem chi tiết + Before/After ở `docs/vn-swing-trading.md` section 2.
- **102 tests pass** (`pytest tests/ -q`).

---

## Kiểm tra từng Milestone

### Milestone 1 — Data Layer ✅
> Week 1-2 | `core/data_manager.py`, `data_sources/`

**Chạy unit + integration tests:**
```bash
pytest tests/unit/ -v
pytest tests/integration/test_data_layer.py -v
```

**Fetch dữ liệu 5 năm (lần đầu — cần internet):**
```bash
python trading_bot.py init-data --years 5
# Kỳ vọng: >= 250/290 mã thành công, hoàn thành < 5 phút
```

**Kiểm tra data quality:**
```bash
python trading_bot.py validate --symbol VCB
python trading_bot.py validate --symbol HPG
# Kỳ vọng: không có warning nghiêm trọng
```

**Chạy daily update (mô phỏng):**
```bash
python trading_bot.py update-daily
# Kỳ vọng: hoàn thành < 60 giây
```

**✅ Milestone 1 đạt khi:** tất cả tests pass + fetch >= 250/290 mã + daily update < 60s

---

### Milestone 2 — Signal & Risk Engine ✅
> Week 3 | `signals/momentum_v1.py`, `core/risk_engine.py`, `core/market_regime.py`

**Hard gates chặn BUY** (xem `docs/vn-swing-trading.md` §1.1):
- `RSI14 > 75` — overbought
- `close < EMA200` — trend filter per-symbol
- `vol / vol_MA20 < 1.5` — yêu cầu volume breakout
- VN30 basket ≤ EMA50 — macro bear filter

**Chạy unit tests:**
```bash
pytest tests/unit/test_momentum_v1.py -v
pytest tests/unit/test_risk_engine.py -v
pytest tests/unit/test_market_regime.py -v
```

**Kiểm tra critical tests (bắt buộc pass 100%):**
```bash
# Look-ahead bias
pytest tests/unit/test_momentum_v1.py::test_no_look_ahead_bias -v

# Volume breakout gate
pytest tests/unit/test_momentum_v1.py::test_volume_breakout_blocks_buy_when_vol_below_1_5x -v
pytest tests/unit/test_momentum_v1.py::test_volume_breakout_allows_buy_when_spike -v

# Circuit breaker
pytest tests/unit/test_risk_engine.py::test_circuit_breaker_triggers_at_150pct -v
pytest tests/unit/test_risk_engine.py::test_circuit_breaker_no_trigger_below_150pct -v

# Trailing stop ratchet
pytest tests/unit/test_risk_engine.py::test_trailing_stop_update_ratchets_monotonically -v
```

**Scan thử 1 mã / toàn thị trường:**
```bash
python trading_bot.py scan --symbol VCB
# Kỳ vọng: in ra SignalResult với score, regime, action, indicators

python trading_bot.py scan
# Kỳ vọng: in trạng thái macro regime (VN30 vs EMA50) + danh sách BUY/SELL
```

**✅ Milestone 2 đạt khi:** look-ahead bias test pass 100% + circuit breaker test pass 100% + volume/trailing tests pass

---

### Milestone 3 — Portfolio Manager & Database
> Week 4 | `core/portfolio_manager.py`, `db/trades.db`

**Chạy unit tests:**
```bash
pytest tests/unit/test_portfolio_manager.py -v
```

**Kiểm tra P&L khớp tính tay:**
```bash
pytest tests/unit/test_portfolio_manager.py::test_realized_pnl_includes_commission_and_slippage -v
pytest tests/unit/test_portfolio_manager.py::test_mdd_calculation -v
```

**Kiểm tra state persist:**
```bash
pytest tests/integration/test_portfolio_db.py -v
# Bao gồm test save → restart → state giống hệt (10 lần)
```

**✅ Milestone 3 đạt khi:** P&L khớp tính tay >= 20 test cases + state persist qua 10 lần restart

---

### Milestone 4 — Backtesting Engine ✅
> Week 5 | `core/backtester.py`, `brokers/simulated_broker.py`, `scripts/backtest_portfolio_vn30.py`

**Chạy unit tests:**
```bash
pytest tests/unit/test_simulated_broker.py -v
pytest tests/unit/test_backtester.py -v
```

**Backtest 1 mã (CLI):**
```bash
python trading_bot.py backtest HPG --years 3
# Kỳ vọng: hoàn thành < 60 giây, in 8 metrics
```

**Backtest toàn bộ walk-forward:**
```bash
python trading_bot.py backtest-all --walk-forward --split 0.7
# Kỳ vọng: báo cáo có cả in-sample và out-of-sample
```

**Portfolio backtest (swing trading lens — đây là baseline chính):**
```bash
python scripts/backtest_portfolio_vn30.py
# 500M VND, max_positions=5, shared cash pool, VN30 universe, 5 năm
# Output:
#   data/backtest_portfolio_vn30_trades.csv
#   data/backtest_portfolio_vn30_equity.csv
#   data/backtest_portfolio_vn30_periodic.csv
# Baseline hiện tại (2026-04-19): CAGR +1.74%, Sharpe 0.261,
#                                  MDD 8.62%, WR 36.74%, PF 1.106
```

**Kiểm tra 8 metrics bắt buộc có trong báo cáo:**
```bash
pytest tests/unit/test_backtester.py::test_all_8_metrics_present_in_report -v
# Metrics: Sharpe, Sortino, IR, MDD, WinRate, ProfitFactor, trades, return
```

**✅ Milestone 4 đạt khi:** backtest HPG 3 năm < 60s + portfolio backtest output khớp với baseline ghi trong `docs/vn-swing-trading.md` §2

---

### Milestone 5 — Scheduler & Bot Core
> Week 6 | `trading_bot.py`, APScheduler

**Chạy unit tests:**
```bash
pytest tests/unit/test_bot_core.py -v
pytest tests/unit/test_scheduler.py -v
```

**Chạy integration tests:**
```bash
pytest tests/integration/test_bot_lifecycle.py -v
```

**Khởi động bot paper trading:**
```bash
python trading_bot.py start
# Kiểm tra logs/bot.log — không có unhandled exception
# Kiểm tra logs/scan.log — có entry sau 15:35
# Kiểm tra state/signal_queue.json — được cập nhật mỗi phiên
```

**Chạy watchdog (tmux/screen):**
```bash
bash watchdog.sh
# Kỳ vọng: bot tự restart trong 30s sau khi crash
```

**✅ Milestone 5 đạt khi:** tất cả tests pass + 14 ngày chạy liên tục không crash

---

### Milestone 6 — Streamlit Dashboard
> Week 7 | `streamlit_app.py`

**Chạy unit tests:**
```bash
pytest tests/unit/test_streamlit_helpers.py -v
```

**Khởi động web UI:**
```bash
streamlit run streamlit_app.py
# Mở browser: http://localhost:8501
```

**Manual checklist:**
- [ ] Trang 1 Dashboard: equity curve, positions table, circuit breaker status
- [ ] Trang 2 Signal Queue: APPROVE/REJECT hoạt động, chart overlay
- [ ] Trang 2 Watchlist: add/remove mã, tối đa 10
- [ ] Trang 3 Config: toggle data_source, Start/Stop bot
- [ ] Trang 4 Reports: metrics khớp tính tay, export CSV
- [ ] Trang 5 Backtest: chạy từ UI, hiển thị 8 metrics
- [ ] DevTools Network tab: không có HTTP call khi dùng UI

**✅ Milestone 6 đạt khi:** unit tests pass + manual checklist 100%

---

### Milestone 7 — Phase 1 Complete (Paper Trading)
> Week 8 | Notifications, Error Handling, E2E

**Chạy unit tests:**
```bash
pytest tests/unit/test_telegram_bot.py -v
pytest tests/unit/test_error_handling.py -v
```

**Chạy 5 E2E scenarios:**
```bash
pytest tests/e2e/test_full_flow.py -v
# Scenario 1: scan → approve → order → fill → position open
# Scenario 2: stop-loss triggered → SELL + notify
# Scenario 3: circuit breaker MDD > 150% → stop all
# Scenario 4: crash → restart → portfolio intact
# Scenario 5: switch YFINANCE → SSI qua config
```

**Kiểm tra Phase 1 criteria sau 60 ngày paper trading:**
```bash
python trading_bot.py report --period 60d
# Mục tiêu (align với baseline hiện tại + roadmap):
#   Sharpe Ratio    >= 1.0   (baseline hiện 0.261)
#   Info Ratio      >= 0     (vs VN-Index)
#   MDD             <= 12%   (baseline hiện 8.62% ✅)
#   Win Rate        >= 40%   (baseline hiện 36.74%)
#   Profit Factor   >= 1.3   (baseline hiện 1.106)
#   Số giao dịch    >= 30
```
Baseline hiện chưa đạt Sharpe/PF target — cần tiếp tục roadmap ở `docs/vn-swing-trading.md` §3.8 (RS vs VN30, MACD zero-line, regime-adaptive TP) trước khi chuyển Phase 2.

**✅ Milestone 7 (Phase 1) đạt khi:** 5 E2E scenarios pass + 60 ngày paper trading đạt tất cả metrics

---

### Milestone 8 — Phase 2 (SSI API — Future)
> Sau khi Phase 1 hoàn thành và có SSI API credentials

**Cấu hình credentials:**
```bash
cp config/.env.example config/.env
# Điền SSI_CONSUMER_ID, SSI_CONSUMER_SECRET, SSI_ACCOUNT
```

**Chạy integration tests với SSI thật:**
```bash
pytest tests/integration/test_ssi_integration.py -v
# Bao gồm: đặt lệnh 1 cổ → hủy → confirm cancelled
```

**Chuyển sang live trading (50M VND):**
```bash
# Sửa config/config.json:
#   "data_source": "SSI"
#   "broker": "SSIBroker"
#   "capital.initial": 50000000
python trading_bot.py start
```

**✅ Milestone 8 đạt khi:** SSI integration tests pass + đặt/hủy lệnh thật 1 cổ thành công

---

## Biến môi trường

```bash
# config/.env (không commit git)
SSI_CONSUMER_ID=your_consumer_id
SSI_CONSUMER_SECRET=your_consumer_secret
SSI_ACCOUNT=your_account_number
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Chạy toàn bộ test suite

```bash
# Unit tests (nhanh, không cần network)
pytest tests/unit/ -v

# Integration tests (mock, không cần network)
pytest tests/integration/ -v -k "not slow"

# Integration tests với real network
pytest tests/integration/ -v -m slow

# E2E tests
pytest tests/e2e/ -v

# Tất cả (trừ slow)
pytest tests/ -v -k "not slow"
```

## CI/CD

GitHub Actions tự động chạy `tests/unit/` cho mỗi push lên `main`.  
Commit mới hơn sẽ cancel run cũ (concurrency group).  
Xem kết quả tại tab **Actions** trên GitHub.
