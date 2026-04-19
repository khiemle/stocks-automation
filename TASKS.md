# Tasks — VN Auto Trading System

> Mỗi deliverable phải đi kèm unit test + integration test trước khi coi là done.
> Chi tiết test cases xem: `test-plan.md`
> Convention: `tests/unit/` cho unit tests, `tests/integration/` cho integration tests

---

## 🔴 Pre-requisites (Resolve Before Coding)

- [ ] Xác nhận SSI FastConnect Data API hỗ trợ OHLCV lịch sử (endpoint, date range tối đa)
- [ ] Xác nhận SSI FastConnect Data API hỗ trợ Intraday OHLCV (endpoint, delay, granularity)
- [ ] Xác nhận SSI API có endpoint khối ngoại (ForeignRoom) hay không
- [ ] Đăng ký SSI iBoard API tại iboard.ssi.com.vn — lấy CONSUMER_ID, CONSUMER_SECRET, PRIVATE_KEY
- [ ] Xác nhận môi trường chạy: Windows, Linux hay macOS
- [ ] Quyết định có cần Telegram bot ngay Phase 1 không
- [ ] Chuẩn bị file danh sách mã tĩnh: `data/universe/HOSE.txt`, `HNX.txt` (~300 mã)

---

## 🟡 Phase 1: Paper Trading (In Progress)

---

### Week 1-2 — Data Layer

**Implement:**
- [x] Khởi tạo project structure theo thư mục trong product-spec.md
- [x] Tạo file danh sách mã tĩnh: `data/universe/HOSE.txt` và `HNX.txt`
- [x] Định nghĩa `DataSourceProtocol` — interface chung cho SSI và yfinance
- [x] Viết `YFinanceClient` — `get_daily_ohlcv`, `get_daily_ohlcv_batch`, `get_intraday_price`, `get_intraday_prices_batch`, `get_universe`, `get_foreign_flow` (trả về None)
- [x] Viết `SSIDataClient` — cùng interface, authenticate, retry logic, token refresh
- [x] Viết `DataManager` — inject DataSource theo config, `get_ohlcv` từ Parquet cache, `update_daily` batch, `validate_data`
- [x] Implement initial data load: `python trading_bot.py init-data --years 5`
- [x] Implement daily update: 6 batch × 50 mã, delay 2-3s giữa batches
- [x] Viết data quality checks (volume=0, giá ngoài biên độ, gap > 15%)

**Unit Tests** (`tests/unit/test_yfinance_client.py`, `test_data_manager.py`):
- [x] `test_get_daily_ohlcv_returns_correct_columns` — DataFrame có đủ date, open, high, low, close, volume
- [x] `test_vn_suffix_applied` — "VCB" → gọi yfinance với "VCB.VN"
- [x] `test_get_daily_ohlcv_batch_returns_all_symbols` — batch 3 mã trả về dict 3 keys
- [x] `test_get_foreign_flow_returns_none` — YFinanceClient trả về None, không crash
- [x] `test_get_universe_reads_from_file` — đọc đúng từ HOSE.txt
- [x] `test_get_ohlcv_reads_from_parquet_cache` — mock network, DataManager đọc từ file
- [x] `test_update_daily_batches_correctly` — 300 mã → 6 batches, delay >= 2s mỗi batch
- [x] `test_validate_data_flags_zero_volume` — volume=0 trong ngày GD → ValidationReport có warning
- [x] `test_validate_data_flags_price_gap` — gap > 15% giữa 2 phiên → flag
- [x] `test_validate_data_flags_out_of_band` — thay đổi > 7% HOSE → flag
- [x] `test_no_future_data_leak` — ⚠️ `df.index.max() <= today` — không có data tương lai

**Integration Tests** (`tests/integration/test_data_layer.py`):
- [x] `test_init_data_creates_parquet_files` — chạy init-data cho 5 mã, kiểm tra file tạo đúng
- [x] `test_daily_update_appends_one_row` — update ngày mới, Parquet thêm đúng 1 row, không duplicate
- [x] `test_data_manager_uses_cache_not_network` — mock YFinanceClient, `get_ohlcv()` không gọi network
- [ ] `test_fetch_250_of_300_symbols_succeed` — integration với yfinance thật, >= 250/300 thành công (cần network, @slow)

**✅ Milestone 1 done khi:** tất cả tests pass + fetch >= 250/300 mã + daily update < 60s

---

### Week 3 — Signal & Risk Engine

**Implement:**
- [x] Định nghĩa `SignalEngineProtocol` + `SignalResult` dataclass (score, regime, action, indicators, confidence)
- [x] Định nghĩa `BrokerProtocol` + dataclasses: `OrderResult`, `OrderStatus`, `AccountBalance`, `StockPosition`
- [x] Viết `MomentumV1` implement `SignalEngineProtocol` — composite score 6 indicators
- [x] Implement `evaluate()` — dùng sau 15:35 với OHLCV đầy đủ
- [x] Implement `evaluate_intraday()` — dùng cho watchlist mỗi 30 phút
- [x] Implement regime detection (TRENDING / VOLATILE / SIDEWAYS)
- [x] Viết bộ lọc loại trừ (volume < 100k, giá < 5,000 VND, T+2, đã trong danh mục)
- [x] Viết `RiskEngine` — ATR position sizing, stop ATR×1.5, TP ATR×4.5, trailing stop
- [x] Implement circuit breaker: MDD_real > 150% MDD_backtest → stop all
- [x] Implement VN-specific rules: T+2, price band HOSE ±7% / HNX ±10%, volume <= 5% ADV

**Unit Tests** (`tests/unit/test_momentum_v1.py`, `test_risk_engine.py`):
- [x] `test_trending_market_returns_high_score` — MA20>MA60, MACD bullish, RSI<70, ADX>25 → score > 0.55
- [x] `test_sideways_market_reduces_score` — ADX < 20 → regime SIDEWAYS, score thấp hơn
- [x] `test_overbought_rsi_blocks_buy` — RSI > 75 → score < 0.55
- [x] `test_low_volume_reduces_score` — vol/MA20 < 0.5 → volume component đóng góp thấp
- [x] `test_missing_foreign_flow_sets_weight_zero` — foreign_flow=None → không crash, weight=0
- [x] `test_score_range` — -1.0 <= score <= 1.0 với bất kỳ OHLCV hợp lệ
- [x] `test_regime_detection_trending` — ADX=28 → TRENDING
- [x] `test_regime_detection_volatile` — ATR/close > 3% → VOLATILE
- [x] `test_no_look_ahead_bias` — ⚠️ CRITICAL: evaluate(df[:T]) == evaluate(df[:T] với full df)
- [x] `test_position_size_2pct_risk` — capital=500M, ATR=1500 → shares đúng công thức
- [x] `test_max_position_cap_at_20pct` — calculated size > 20% portfolio → capped
- [x] `test_stop_loss_check_hose_price_band` — stop < close×0.93 → cảnh báo, không entry
- [x] `test_stop_loss_check_hnx_price_band` — stop < close×0.90 → cảnh báo, không entry
- [x] `test_t2_enforcement_blocks_sell` — buy today → SELL bị reject trong 2 ngày làm việc
- [x] `test_order_size_max_5pct_adv` — qty > 5% ADV → capped
- [x] `test_circuit_breaker_triggers_at_150pct` — real_MDD = 1.6× backtest → stop_all()
- [x] `test_circuit_breaker_no_trigger_below_150pct` — real_MDD = 1.4× → không stop
- [x] `test_weekly_loss_limit_warning_at_1_5pct` — weekly PnL = -1.6% → cảnh báo
- [x] `test_weekly_loss_limit_stop_at_3pct` — weekly PnL = -3.1% → dừng vị thế mới
- [x] `test_low_volume_symbol_excluded` — vol_MA20 = 80k → không qua filter
- [x] `test_penny_stock_excluded` — close = 4,500 → không qua filter
- [x] `test_existing_position_excluded` — symbol đã trong portfolio → không BUY

**Integration Tests** (`tests/integration/test_signal_risk.py`):
- [x] `test_scan_single_symbol_end_to_end` — load Parquet VCB, chạy MomentumV1, trả về SignalResult hợp lệ
- [x] `test_risk_engine_with_real_atr` — dùng data VCB thật, tính ATR và position size, kết quả trong biên hợp lý

**✅ Milestone 2 done khi:** look-ahead bias test pass 100% + circuit breaker test pass 100%

---

### Week 4 — Portfolio Manager & Database

**Implement:**
- [x] Tạo SQLite schema: `trades`, `orders`, `scan_logs`, `equity_history`
- [x] Viết `PortfolioManager` — open/close positions, P&L tracking, persist portfolio.json + trades.db
- [x] Implement metrics: Sharpe, Sortino, Information Ratio, MDD, Win Rate, Profit Factor
- [x] Implement weekly P&L tracking và weekly loss limit alert (-3%)

**Unit Tests** (`tests/unit/test_portfolio_manager.py`):
- [x] `test_realized_pnl_includes_commission_and_slippage` — PnL = gross - 0.15%×2 sides - slippage cả 2 chiều
- [x] `test_unrealized_pnl_uses_current_price` — position @ 50k, current 53k → unrealized đúng
- [x] `test_total_equity_is_cash_plus_market_value` — equity = cash + sum(qty × price)
- [x] `test_win_rate_calculation` — 6 wins, 4 losses → 0.60
- [x] `test_profit_factor` — wins=15M, losses=8M → 1.875
- [x] `test_mdd_calculation` — equity 100→120→90→110 → MDD = 25%
- [x] `test_sharpe_ratio_positive_for_stable_curve` — equity tăng ổn định → Sharpe > 0
- [x] `test_weekly_pnl_resets_on_monday` — equity_week_start cập nhật thứ 2
- [x] `test_trade_written_to_sqlite_with_all_fields` — close position → record đủ fields
- [x] `test_no_duplicate_trade_on_double_close` — đóng position 2 lần → chỉ 1 record
- [x] `test_portfolio_state_survives_restart` — save → reload → state giống hệt

**Integration Tests** (`tests/integration/test_portfolio_db.py`):
- [x] `test_open_close_position_flow` — mở vị thế, cập nhật stop, đóng → DB record đúng toàn bộ
- [x] `test_equity_history_recorded_daily` — simulate 5 ngày → 5 rows trong equity_history
- [x] `test_pnl_matches_manual_calculation` — 3 trades mẫu tính tay, so sánh với PortfolioManager

**✅ Milestone 3 done khi:** P&L khớp tính tay trên >= 20 test cases + state persist qua 10 lần restart

---

### Week 5 — Backtesting Engine

**Implement:**
- [x] Viết `SimulatedBroker` implement `BrokerProtocol` — fill T+1 open, commission 0.15% + slippage 0.1%
- [x] Viết `Backtester` — walk-forward validation (70/30 split)
- [x] Implement backtest CLI: `python trading_bot.py backtest HPG --years 3`
- [x] Implement backtest-all CLI: `python trading_bot.py backtest-all --walk-forward --split 0.7`
- [x] Verify 8 metrics bắt buộc

**Unit Tests** (`tests/unit/test_simulated_broker.py`, `test_backtester.py`):
- [x] `test_buy_fills_at_next_bar_open` — signal ngày T → fill tại OPEN T+1, không phải close T
- [x] `test_sell_fills_at_next_bar_open` — tương tự cho SELL
- [x] `test_t2_blocks_sell_within_2_business_days` — buy T, sell T+1 → Rejected
- [x] `test_commission_0_15pct_per_side` — buy 100tr → deduct 150k
- [x] `test_slippage_0_1pct_applied` — fill = open × 1.001 (BUY) / × 0.999 (SELL)
- [x] `test_account_balance_decreases_on_buy` — cash giảm đúng sau buy
- [x] `test_walk_forward_split_is_70_30` — 5 năm → train 3.5 năm, test 1.5 năm
- [x] `test_no_data_leak_train_to_test` — train set không chứa ngày thuộc test set
- [x] `test_out_of_sample_metrics_in_report` — report có cả in-sample và out-of-sample
- [x] `test_all_8_metrics_present_in_report` — Sharpe, Sortino, IR, MDD, WinRate, PF, trades, return đều có

**Integration Tests** (`tests/integration/test_backtester.py`):
- [x] `test_backtest_hpg_3_years_completes_under_60s` — performance test
- [x] `test_backtest_pnl_matches_manual_on_3_trades` — so sánh 3 trades tính tay
- [x] `test_backtest_matches_paper_simulation_on_same_data` — ⚠️ anti-bias: kết quả phải giống nhau

**✅ Milestone 4 done khi:** backtest HPG 3 năm < 60s + kết quả khớp paper simulation

---

### Week 6 — Scheduler & Bot Core

**Implement:**
- [x] Viết `build_bot()` — DI: đọc config, inject DataSource + SignalEngine(s) + Broker
- [x] Viết `ENGINE_REGISTRY` — đăng ký SignalEngine theo tên
- [x] Setup APScheduler với timezone Asia/Ho_Chi_Minh
- [x] Implement daily scan job (15:35): batch fetch → scan → write signal_queue.json
- [x] Implement intraday monitor job (30 phút): portfolio (≤5) + watchlist (≤10) trong 1 batch
- [x] Implement intraday watchlist signal (source: INTRADAY)
- [x] Implement order placement job (09:10)
- [x] Implement cancel unfilled orders job (14:30)
- [x] Implement equity snapshot (15:10) + weekly reset (thứ 2 8:00)
- [x] Implement signal expiry (08:30)
- [x] Viết watchdog script (`watchdog.sh`) + state recovery

**Unit Tests** (`tests/unit/test_bot_core.py`, `test_scheduler.py`):
- [x] `test_build_bot_injects_yfinance_client` — config data_source=YFINANCE → bot.data_source is YFinanceClient
- [x] `test_build_bot_injects_simulated_broker` — config broker=SimulatedBroker → đúng class
- [x] `test_build_bot_unknown_engine_raises_key_error` — engine không có trong registry → lỗi rõ ràng
- [x] `test_engine_registry_has_momentum_v1` — ENGINE_REGISTRY["MomentumV1"] không None
- [x] `test_daily_scan_writes_pending_signals` — mock data + engine → signal_queue.json có PENDING
- [x] `test_signal_expiry_marks_old_signals_expired` — signal hôm qua chưa approve → EXPIRED
- [x] `test_order_placement_skips_pending_signals` — chỉ đặt APPROVED, bỏ qua PENDING
- [x] `test_cancel_unfilled_called_after_1430` — mock time 14:31 → cancel_order() được gọi
- [x] `test_intraday_monitor_triggers_sell_on_stop` — current_price <= stop_loss → place_order(SELL)
- [x] `test_intraday_monitor_triggers_sell_on_tp` — current_price >= take_profit → place_order(SELL)
- [x] `test_intraday_trailing_stop_updates` — price tăng > 1R → stop_loss mới trong portfolio.json
- [x] `test_watchlist_intraday_signal_created_when_score_high` — score=0.63 → thêm INTRADAY signal
- [x] `test_recover_state_restores_portfolio` — portfolio.json tồn tại → positions load đúng
- [x] `test_recover_state_syncs_pending_orders` — ORDER_PLACED signals → check status từ broker

**Integration Tests** (`tests/integration/test_bot_lifecycle.py`):
- [x] `test_full_daily_scan_cycle` — trigger daily scan, verify signal_queue.json được tạo đúng
- [x] `test_order_placement_after_approve` — approve signal → sáng hôm sau SimulatedBroker nhận lệnh
- [x] `test_bot_recovers_after_simulated_crash` — kill + restart → portfolio giữ nguyên, không duplicate

**Manual Test — 2 tuần liên tục:**
- [ ] Bot khởi động mỗi ngày không lỗi, scan.log có entry lúc 15:35
- [ ] signal_queue.json được cập nhật mỗi phiên
- [ ] Intraday log ghi đúng mỗi 30 phút trong giờ GD
- [ ] Không có unhandled exception trong bot.log trong 14 ngày

**✅ Milestone 5 done khi:** tất cả unit/integration tests pass + 14 ngày không crash

---

### Week 7 — Streamlit Dashboard

**Implement:**
- [x] Khởi tạo `streamlit_app.py` — read-only từ DB/JSON, viết config.json và signal_queue.json
- [x] Trang 1: Dashboard — equity, positions table, circuit breaker status, equity curve vs VN-Index
- [x] Trang 2: Signal Queue — PENDING (EOD + INTRADAY), APPROVE/REJECT, chart overlay
- [x] Trang 2: Watchlist manager — add/remove, tối đa 10 mã, lưu config.json
- [x] Trang 3: Config — bot control, capital/signal/risk params, data_source toggle, save/reset
- [x] Trang 4: Reports — metrics, trade log, export CSV, benchmark chart
- [x] Trang 5: Backtest — chạy từ UI, hiển thị kết quả in/out-of-sample

**Unit Tests** (`tests/unit/test_streamlit_helpers.py`):
- [x] `test_approve_signal_updates_status_to_approved` — gọi helper function → status = APPROVED trong file
- [x] `test_reject_signal_updates_status_to_rejected`
- [x] `test_add_to_watchlist_saves_to_config` — thêm mã → config.json có mã đó
- [x] `test_watchlist_max_10_enforced` — thêm mã thứ 11 → raise error
- [x] `test_save_config_persists_all_fields` — save → reload → tất cả fields giữ nguyên
- [x] `test_streamlit_reads_only_no_api_call` — mock broker + data_source → không có HTTP call khi load UI

**Manual Test Checklist** (`test-plan.md §Milestone 6`):
- [ ] Trang 1: equity đúng, circuit breaker đổi màu, positions table đúng, chart render
- [ ] Trang 2: APPROVE/REJECT hoạt động, EOD/INTRADAY label đúng, watchlist add/remove/persist
- [ ] Trang 3: data_source toggle ghi config, Start/Stop bot hoạt động, SSI status hiển thị
- [ ] Trang 4: metrics khớp tính tay, export CSV đúng format
- [ ] Trang 5: backtest chạy từ UI, kết quả hiển thị đủ 8 metrics
- [ ] Toàn bộ: không có network call khi dùng UI (kiểm tra browser DevTools)

**✅ Milestone 6 done khi:** unit tests pass + manual checklist 100% pass

---

### Week 8 — Notifications & Error Handling

**Implement:**
- [ ] Setup Telegram bot: BUY signal, lệnh khớp, stop/TP hit, circuit breaker, daily summary 16:00
- [ ] Implement SSI API error handling: retry 3 lần, exponential backoff (1s, 2s, 4s)
- [ ] Setup logging: bot.log, trades.log, errors.log, scan.log
- [ ] Implement Implementation Shortfall tracking (signal_price, order_price, fill_price, delay_cost)

**Unit Tests** (`tests/unit/test_telegram_bot.py`, `test_error_handling.py`):
- [ ] `test_telegram_notify_buy_signal_format` — message có symbol, score, giá, link web
- [ ] `test_telegram_notify_stop_loss_hit` — message có symbol, giá exit, PnL
- [ ] `test_telegram_notify_circuit_breaker` — message có MDD%, ngưỡng, trạng thái STOPPED
- [ ] `test_telegram_notify_daily_summary_at_1600` — gọi đúng lúc 16:00, có tóm tắt ngày
- [ ] `test_retry_3_times_on_timeout` — mock timeout → gọi lại 3 lần, sau đó raise
- [ ] `test_exponential_backoff_delays` — delay lần lượt 1s, 2s, 4s
- [ ] `test_401_triggers_token_refresh` — response 401 → refresh token → retry
- [ ] `test_api_error_does_not_crash_bot` — lỗi SSI API → log vào errors.log, bot tiếp tục chạy
- [ ] `test_implementation_shortfall_calculated` — fill_price - signal_price = delay_cost đúng

**Integration Tests** (`tests/integration/test_notifications.py`):
- [ ] `test_telegram_message_delivered` — gửi tin thật đến bot test, xác nhận nhận được
- [ ] `test_all_orders_logged_to_trades_log` — đặt 3 lệnh simulated → 3 entries trong trades.log

**E2E Tests — 5 Scenarios** (`tests/e2e/test_full_flow.py`):
- [ ] `test_scenario_1_happy_path` — full flow: scan → signal → approve → order → fill → position open
- [ ] `test_scenario_2_stop_loss_triggered` — position open → giả lập price drop → SELL + notify + trade closed
- [ ] `test_scenario_3_circuit_breaker` — giả lập MDD vượt 150% → stop all + alert + no new orders
- [ ] `test_scenario_4_crash_and_recovery` — kill process → restart → portfolio intact, no duplicate
- [ ] `test_scenario_5_data_source_switch` — đổi YFINANCE → SSI trên config → bot dùng SSIDataClient sau restart

**✅ Milestone 7 (Phase 1 complete) khi:** tất cả 5 E2E scenarios pass + 60 ngày paper trading đạt metrics

---

### Phase 1 Milestone Checklist

- [ ] >= 60 ngày paper trading
- [ ] Sharpe Ratio >= 1.0
- [ ] Information Ratio vs VN-Index >= 0
- [ ] MDD trong paper trading <= 15%
- [ ] Win rate >= 52%
- [ ] Số giao dịch >= 30
- [ ] 0 bug nghiêm trọng
- [ ] Tất cả unit tests pass (CI green)
- [ ] Tất cả integration tests pass
- [ ] 5 E2E scenarios pass thủ công

---

## 🔵 Phase 2: Semi-Auto với SSI API (Future)

**Implement:**
- [ ] Đăng ký SSI API và test với lệnh nhỏ (1 cổ phiếu)
- [ ] Viết `SSIBroker` implement `BrokerProtocol` — place_order, cancel_order, get_order_status, get_account_balance, get_stock_positions
- [ ] Tích hợp signal_queue → SSI API order placement thực tế
- [ ] Implement T+2 enforcement thực tế với SSI account
- [ ] Real portfolio reconciliation từ SSI account
- [ ] Set initial_capital = 50,000,000 VND

**Unit Tests** (`tests/unit/test_ssi_broker.py`):
- [ ] `test_ssi_broker_implements_broker_protocol` — isinstance check với Protocol
- [ ] `test_place_order_builds_correct_request_body` — verify JSON payload đúng SSI spec
- [ ] `test_cancel_order_builds_correct_request` — verify endpoint và params
- [ ] `test_auth_token_included_in_header` — mọi request có Authorization: Bearer
- [ ] `test_retry_on_ssi_timeout` — mock timeout → retry 3 lần
- [ ] `test_401_triggers_token_refresh_and_retry`

**Integration Tests** (`tests/integration/test_ssi_integration.py`) — cần API key thật:
- [ ] `test_authenticate_returns_valid_token` — credentials hợp lệ → JWT token
- [ ] `test_get_daily_ohlcv_matches_iboard` — so sánh với giá trên iBoard UI
- [ ] `test_place_and_cancel_1_share` — đặt lệnh 1 cổ → cancel → confirm cancelled
- [ ] `test_get_account_balance_returns_positive` — cash > 0
- [ ] `test_portfolio_reconciliation` — portfolio.json khớp SSIBroker.get_stock_positions()

**✅ Milestone 8 done khi:** SSI integration tests pass + đặt/hủy lệnh thật 1 cổ thành công

---

## ✅ Done

<!-- Completed tasks move here -->
