# Test Plan: VN Auto Trading System

> Phiên bản: 1.0
> Tham khảo: product-spec.md, system-design.md

---

## Tổng quan chiến lược

```
Pyramid:
        /   Manual E2E   \     Phase transition gates
       /   Integration    \    Cross-component flows
      /     Unit Tests     \   Component-level logic
```

**Nguyên tắc:**
- Unit test tập trung vào **business logic** — không test framework code
- Integration test kiểm tra **data flow giữa các component**
- Manual E2E kiểm tra **toàn bộ hệ thống** trước khi chuyển phase
- Ưu tiên test cao nhất: **look-ahead bias**, **P&L tính sai**, **circuit breaker không kích hoạt**

---

## Phase 1 — Paper Trading

### Milestone 1 — Data Layer (Week 1-2)

**Mục tiêu:** Đảm bảo data fetch, lưu trữ, và validate hoạt động đúng trước khi build Signal Engine.

#### Unit Tests

**YFinanceClient**

| Test | Input | Expected |
|---|---|---|
| `test_get_daily_ohlcv_returns_correct_columns` | symbol="VCB", 30 ngày | DataFrame có đủ: date, open, high, low, close, volume |
| `test_vn_suffix_applied` | symbol="HPG" | Gọi yfinance với "HPG.VN" |
| `test_get_daily_ohlcv_batch_returns_all_symbols` | ["VCB", "HPG", "VHM"] | Dict với 3 keys, mỗi key là DataFrame |
| `test_get_foreign_flow_returns_none` | bất kỳ | None (không crash) |
| `test_get_universe_reads_from_file` | exchange="HOSE" | List[str] đọc từ `data/universe/HOSE.txt` |

**DataManager**

| Test | Input | Expected |
|---|---|---|
| `test_get_ohlcv_reads_from_parquet_cache` | symbol="VCB", days=120 | Đọc file, không gọi network |
| `test_update_daily_batches_correctly` | 300 mã | Chia thành 6 batch × 50, mỗi batch delay >= 2s |
| `test_validate_data_flags_zero_volume` | DataFrame có ngày volume=0 | ValidationReport có warning |
| `test_validate_data_flags_price_gap` | Gap giá > 15% giữa 2 phiên | ValidationReport có flag |
| `test_validate_data_flags_out_of_band` | Giá thay đổi > 7% HOSE | ValidationReport có warning |

```python
# Ví dụ: test look-ahead safety — DataManager không trả về data tương lai
def test_no_future_data_leak(data_manager):
    df = data_manager.get_ohlcv("VCB", days=120)
    today = pd.Timestamp.today().normalize()
    assert df.index.max() <= today, "Data contains future dates — look-ahead bias!"
```

#### Integration Tests

| Test | Mô tả |
|---|---|
| `test_init_data_creates_parquet_files` | Chạy `init-data --years 5` cho 5 mã, kiểm tra file `.parquet` được tạo |
| `test_daily_update_appends_correctly` | Update ngày mới, kiểm tra Parquet có thêm 1 row và không có duplicate |
| `test_data_manager_uses_cache_not_network` | Mock network, `get_ohlcv()` phải đọc từ Parquet không gọi internet |

**✅ Milestone 1 pass khi:**
- 100% unit tests pass
- Fetch thành công >= 250/300 mã (một số mã có thể không có trên yfinance)
- Parquet files tạo đúng cấu trúc, không có duplicate dates
- Daily update chạy < 60 giây cho 300 mã

---

### Milestone 2 — Signal & Risk Engine (Week 3)

**Mục tiêu:** Đảm bảo tín hiệu tính đúng và **không có look-ahead bias**.

#### Unit Tests

**MomentumV1 — Correctness**

| Test | Mô tả |
|---|---|
| `test_trending_market_returns_high_score` | OHLCV với MA20 > MA60, MACD bullish, RSI < 70, ADX > 25 → score > 0.55 |
| `test_sideways_market_reduces_score` | ADX < 20 → regime = SIDEWAYS, score giảm so với trending |
| `test_overbought_rsi_blocks_buy` | RSI > 75 → score < 0.55 (không BUY vào đỉnh) |
| `test_low_volume_reduces_score` | vol/MA20 < 0.5 → volume component đóng góp thấp |
| `test_missing_foreign_flow_sets_weight_zero` | foreign_flow=None → weight khối ngoại = 0, không crash |
| `test_score_range` | Bất kỳ OHLCV hợp lệ | -1.0 <= score <= 1.0 |
| `test_regime_detection_trending` | ADX=28 | regime = "TRENDING" |
| `test_regime_detection_volatile` | ATR/close > 3% | regime = "VOLATILE" |

**MomentumV1 — Look-ahead Bias (Critical)**

```python
def test_no_look_ahead_bias(momentum_v1):
    """
    Chạy evaluate() với DataFrame cắt tại ngày T.
    Kết quả phải giống hệt khi chạy với DataFrame đầy đủ đến ngày T.
    Nếu khác → có look-ahead bias.
    """
    full_df = load_ohlcv("VCB", days=120)
    cut_df = full_df.iloc[:-5]  # Cắt bỏ 5 ngày cuối

    result_full = momentum_v1.evaluate(full_df.iloc[:-5])  # Dùng cùng window
    result_cut = momentum_v1.evaluate(cut_df)

    assert result_full.score == pytest.approx(result_cut.score, abs=0.001), \
        "Look-ahead bias detected in MomentumV1!"
```

**RiskEngine**

| Test | Input | Expected |
|---|---|---|
| `test_position_size_2pct_risk` | capital=500M, ATR=1500, stop_mult=1.5 | shares = floor(10M / 2250) |
| `test_max_position_cap` | Calculated shares > 20% portfolio | Capped tại 20% |
| `test_stop_loss_above_price_band_hose` | stop < close × 0.93 | Cảnh báo, không entry |
| `test_stop_loss_above_price_band_hnx` | stop < close × 0.90 | Cảnh báo, không entry |
| `test_t2_blocks_sell` | entry_date = today | Không cho SELL trong 2 ngày làm việc |
| `test_order_size_max_5pct_adv` | Calculated qty > 5% ADV | Capped tại 5% ADV |
| `test_circuit_breaker_triggers` | real_MDD = 1.6 × backtest_MDD | stop_all_new_positions() được gọi |
| `test_circuit_breaker_not_triggers` | real_MDD = 1.4 × backtest_MDD | Không stop |
| `test_weekly_loss_limit_warning` | weekly_pnl = -1.6% | Cảnh báo (không dừng) |
| `test_weekly_loss_limit_stop` | weekly_pnl = -3.1% | Dừng thêm vị thế mới |

**Exclusion filters**

| Test | Mô tả |
|---|---|
| `test_low_volume_symbol_excluded` | vol_MA20 = 80,000 < 100,000 | Không qua BUY filter |
| `test_penny_stock_excluded` | close = 4,500 < 5,000 VND | Không qua BUY filter |
| `test_existing_position_excluded` | Symbol đã trong portfolio | Không tạo BUY signal |

**✅ Milestone 2 pass khi:**
- Look-ahead bias test pass 100%
- Signal score hợp lý: cổ phiếu đang trending mạnh (HPG giai đoạn tăng) score > 0.55
- Position sizing đúng trên ít nhất 20 test cases với capital/ATR khác nhau
- Circuit breaker kích hoạt đúng 100% trường hợp

---

### Milestone 3 — Portfolio Manager & Database (Week 4)

**Mục tiêu:** Đảm bảo P&L tracking chính xác và persist state đúng.

#### Unit Tests

**PortfolioManager — P&L**

| Test | Mô tả |
|---|---|
| `test_realized_pnl_includes_commission` | Buy 1000 cổ @ 50k, sell @ 55k | PnL = 5M - 0.15%×50M - 0.15%×55M - slippage |
| `test_unrealized_pnl_uses_current_price` | Position @ 50k, current_price=53k | unrealized = 3k × shares |
| `test_total_equity_cash_plus_positions` | cash=200M + 2 positions | equity = cash + sum(market_value) |
| `test_win_rate_calculation` | 6 wins, 4 losses | win_rate = 0.60 |
| `test_profit_factor` | total_wins=15M, total_losses=8M | profit_factor = 1.875 |
| `test_sharpe_ratio_positive_for_good_equity_curve` | Equity tăng ổn định | Sharpe > 1.0 |
| `test_mdd_calculation` | Equity: 100→120→90→110 | MDD = (120-90)/120 = 25% |

**State persistence**

| Test | Mô tả |
|---|---|
| `test_portfolio_survives_restart` | Save → load lại | State giữ nguyên 100% |
| `test_trade_written_to_sqlite` | Close position | Trade record trong `trades.db` đủ fields |
| `test_no_duplicate_trades` | Close position 2 lần (lỗi) | Chỉ 1 record trong DB |

**✅ Milestone 3 pass khi:**
- P&L tính đúng bao gồm phí 0.15%/chiều + slippage 0.1% (so sánh với tính tay)
- State persist qua 10 lần restart không bị mất dữ liệu
- Metrics (Sharpe, MDD, Win Rate) khớp với tính tay trên tập data mẫu 20 trades

---

### Milestone 4 — Backtesting Engine (Week 5)

**Mục tiêu:** Backtester tạo ra kết quả tin cậy, không bias, chi phí đúng.

#### Unit Tests

**SimulatedBroker**

| Test | Mô tả |
|---|---|
| `test_buy_fills_at_next_open` | Signal ngày T | Fill tại giá OPEN ngày T+1 (không phải close T) |
| `test_sell_fills_at_next_open` | SELL signal ngày T | Fill tại OPEN T+1 |
| `test_t2_blocks_sell_before_settlement` | Buy ngày T, sell ngày T+1 | Rejected — T+2 chưa đủ |
| `test_commission_deducted` | Buy 100tr | commission = 150,000 VND (0.15%) |
| `test_slippage_applied` | fill_price | fill_price = open × 1.001 (BUY) hoặc × 0.999 (SELL) |
| `test_account_balance_decreases_on_buy` | Buy 50tr | cash giảm 50tr + phí |

**Backtester — Walk-forward**

| Test | Mô tả |
|---|---|
| `test_walk_forward_split_70_30` | 5 năm data | Train = 3.5 năm, test = 1.5 năm |
| `test_no_data_leak_between_train_test` | | Train set không chứa ngày thuộc test set |
| `test_out_of_sample_metrics_reported` | | Report có cả in-sample và out-of-sample |
| `test_metrics_all_present` | Backtest xong | Sharpe, Sortino, IR, MDD, WinRate, PF, trade count đều có |

**Anti-bias checks (Critical)**

```python
def test_backtest_matches_paper_trading_on_same_data():
    """
    Chạy backtest và paper trading trên cùng data, cùng strategy.
    Kết quả phải giống nhau (trong biên độ nhỏ do floating point).
    Nếu khác nhiều → có bug trong SimulatedBroker.
    """
    backtest_trades = run_backtest("VCB", "2023-01-01", "2023-12-31")
    paper_trades = run_paper_simulation("VCB", "2023-01-01", "2023-12-31")
    assert len(backtest_trades) == len(paper_trades)
    for bt, pt in zip(backtest_trades, paper_trades):
        assert bt.entry_price == pytest.approx(pt.entry_price, rel=0.001)
```

**✅ Milestone 4 pass khi:**
- Backtest HPG 3 năm hoàn thành < 60 giây
- Backtest result khớp tính tay trên 3 trades mẫu (cùng entry/exit date, đúng phí)
- Out-of-sample metrics được báo cáo, không dùng test data để optimize
- Nếu strategy không đạt ngưỡng (Sharpe < 1.0 trên out-of-sample) → đây là tín hiệu cần tune, không phải lỗi test

---

### Milestone 5 — Scheduler & Bot Core (Week 6)

**Mục tiêu:** Bot chạy ổn định liên tục 2 tuần không crash, state recover đúng.

#### Unit Tests

**build_bot() — Dependency Injection**

| Test | Mô tả |
|---|---|
| `test_build_bot_yfinance_mode` | config: data_source="YFINANCE" | bot.data_source là YFinanceClient |
| `test_build_bot_simulated_broker` | config: broker="SimulatedBroker" | bot.broker là SimulatedBroker |
| `test_build_bot_unknown_engine_raises` | config: signal_engines=[{"name":"Unknown"}] | KeyError rõ ràng |
| `test_engine_registry_contains_momentum_v1` | | ENGINE_REGISTRY["MomentumV1"] không None |

**Scheduler jobs**

| Test | Mô tả |
|---|---|
| `test_daily_scan_writes_signal_queue` | Mock data + signal engine | signal_queue.json được tạo với status PENDING |
| `test_signal_expiry_at_0830` | Signal từ hôm qua chưa approve | status → EXPIRED |
| `test_order_placement_only_approved` | Queue có APPROVED + PENDING | Chỉ đặt lệnh cho APPROVED |
| `test_cancel_unfilled_at_1430` | Order status = PLACED sau 14:30 | cancel_order() được gọi |
| `test_intraday_monitor_checks_stop` | current_price <= stop_loss | place_order(SELL) được gọi |
| `test_intraday_monitor_checks_tp` | current_price >= take_profit | place_order(SELL) được gọi |
| `test_intraday_monitor_updates_trailing_stop` | price tăng > 1R | stop_loss được update trong portfolio.json |
| `test_watchlist_signal_added_when_score_high` | Watchlist symbol score=0.63 | Signal INTRADAY thêm vào queue |

**State Recovery**

| Test | Mô tả |
|---|---|
| `test_recover_state_loads_portfolio` | portfolio.json tồn tại | Positions load đúng sau restart |
| `test_recover_state_checks_pending_orders` | Order status ORDER_PLACED | Status được sync từ broker |

#### Integration Tests — 2 tuần liên tục

```
Checklist chạy paper trading 14 ngày:
□ Bot khởi động mỗi ngày không lỗi
□ Daily scan chạy đúng 15:35 mỗi ngày (kiểm tra scan.log)
□ signal_queue.json được ghi mỗi phiên
□ Intraday monitor log mỗi 30 phút trong giờ giao dịch
□ Không có "unhandled exception" trong bot.log
□ portfolio.json cập nhật đúng sau mỗi simulated trade
□ equity_history có 1 record mỗi ngày
```

**✅ Milestone 5 pass khi:**
- 14 ngày không crash
- Tất cả scheduler jobs chạy đúng giờ (sai <= 1 phút)
- Mỗi ngày có ít nhất 1 entry trong scan.log
- Stop/TP simulation kích hoạt đúng khi test thủ công với giá override

---

### Milestone 6 — Streamlit Dashboard (Week 7)

**Mục tiêu:** UI hiển thị đúng dữ liệu, không gọi API trực tiếp, không crash.

#### Manual Test Checklist

**Trang 1 — Dashboard**
```
□ Equity hiển thị đúng = cash + sum(positions × current_price)
□ Circuit breaker indicator đổi màu khi MDD > 80% ngưỡng (WARNING)
□ Positions table đúng số cổ phiếu, entry price, P&L%
□ Equity curve vs VN-Index render không lỗi
□ Page reload không gọi SSI/yfinance API (kiểm tra network tab)
```

**Trang 2 — Signal Queue**
```
□ Hiển thị đủ PENDING signals từ signal_queue.json
□ Label "EOD" và "INTRADAY" hiển thị đúng
□ APPROVE button → status đổi thành APPROVED trong file
□ REJECT button → status đổi thành REJECTED
□ Watchlist: thêm mã mới → lưu vào config.json
□ Watchlist: xóa mã → xóa khỏi config.json
□ Tối đa 10 mã trong watchlist (disable nút Add nếu đủ 10)
```

**Trang 3 — Config**
```
□ Data source toggle: đổi YFINANCE ↔ SSI → ghi vào config.json
□ Start Bot → bot_running = true trong config
□ Stop Bot → bot_running = false
□ Save Config → tất cả thay đổi persist
□ Reset to Default → về giá trị mặc định
□ SSI connection status hiển thị đúng (OK/Error)
```

**Trang 4 — Reports**
```
□ Metrics tính đúng (so sánh với tính tay trên trade log)
□ Export CSV tải xuống đúng format
□ Filter theo time range hoạt động
□ Portfolio vs VN-Index chart đúng ngày
```

**Trang 5 — Backtest**
```
□ Chạy backtest từ UI → progress hiển thị
□ Kết quả hiển thị đủ 8 metrics
□ In-sample vs out-of-sample chart đúng
```

**✅ Milestone 6 pass khi:**
- Tất cả checklist trên pass thủ công
- Không có error trong browser console khi sử dụng bình thường
- Approve signal trên UI → bot đọc được và đặt lệnh đúng ở sáng hôm sau

---

### Milestone 7 — End-to-End Paper Trading (Week 8)

**Mục tiêu:** Hệ thống hoạt động end-to-end hoàn chỉnh trong môi trường paper trading.

#### E2E Test Scenarios

**Scenario 1: Full happy path**
```
1. 15:35 — Bot fetch data, MomentumV1 tìm được BUY signal (HPG, score=0.67)
2. signal_queue.json có entry HPG status=PENDING
3. Telegram nhận notification
4. User mở web, thấy signal HPG trên Trang 2
5. User bấm APPROVE → status = APPROVED
6. 09:10 sáng hôm sau — Bot đọc queue, gọi SimulatedBroker.place_order()
7. SimulatedBroker fill tại giá OPEN ngày đó
8. portfolio.json có position HPG mới
9. Trang 1 Dashboard hiển thị position HPG
10. Intraday monitor: 30 phút sau, kiểm tra stop/TP
```

**Scenario 2: Stop-loss triggered**
```
1. Có position HPG với stop_loss = 24,000
2. Giả lập current_price = 23,500 (dưới stop)
3. Bot phải gọi place_order(SELL) trong vòng 30 phút
4. Position đóng với exit_reason = STOP_LOSS
5. Trade ghi vào trades.db
6. Telegram notify "⛔ Stop-loss hit: HPG"
7. Dashboard không còn HPG trong Active Positions
```

**Scenario 3: Circuit breaker**
```
1. Set backtest_MDD = 10% trong portfolio.json
2. Simulate real_MDD = 16% (> 150% × 10%)
3. Bot phải dừng ALL new positions
4. signal_queue.json không được thêm APPROVED nào
5. Dashboard circuit breaker indicator = 🛑 STOPPED
6. Telegram alert khẩn cấp
```

**Scenario 4: Bot crash và recover**
```
1. Kill process bot giữa chừng
2. Khởi động lại
3. recover_state() load đúng portfolio
4. Pending orders được check status
5. Scheduler resume đúng jobs
6. Không mất trade nào, không duplicate
```

**Scenario 5: Data source switch**
```
1. Đang chạy data_source=YFINANCE
2. Đổi sang SSI trên Config UI
3. Bot restart (scheduler cycle tiếp theo)
4. Daily scan dùng SSIDataClient
5. Foreign flow signal được enable
6. Kết quả scan log ghi đúng source
```

**✅ Milestone 7 (Phase 1 complete) pass khi:**
- Tất cả 5 scenarios pass thủ công
- Bot chạy liên tục >= 60 ngày
- Metrics đạt ngưỡng: Sharpe >= 1.0, MDD <= 15%, Win rate >= 52%
- Số giao dịch >= 30
- 0 unhandled exception trong 60 ngày

---

## Phase 2 — Semi-Auto với SSI API

### Milestone 8 — SSI Integration

**Mục tiêu:** `SSIBroker` và `SSIDataClient` hoạt động đúng với API thật trước khi giao dịch bằng tiền thật.

#### Integration Tests (cần API key thật)

**SSIDataClient**

| Test | Mô tả |
|---|---|
| `test_authenticate_returns_token` | Credentials hợp lệ | JWT token trả về, không rỗng |
| `test_token_auto_refresh` | Token hết hạn | Request tiếp theo vẫn thành công |
| `test_get_daily_ohlcv_real_symbol` | symbol="VCB", 30 ngày | DataFrame có đủ cột, không có null |
| `test_get_intraday_real` | symbol="VCB" trong giờ GD | Giá trả về trong biên độ hợp lý |
| `test_retry_on_timeout` | Mock timeout lần 1 | Tự retry, thành công lần 2 |
| `test_rate_limit_handled` | 10 request liên tiếp nhanh | Không bị block, retry đúng |

**SSIBroker — Test với lệnh nhỏ (1 cổ phiếu)**

| Test | Mô tả |
|---|---|
| `test_place_order_returns_order_id` | BUY 1 cổ VCB | order_id hợp lệ từ SSI |
| `test_get_order_status` | order_id từ test trên | Status = PLACED hoặc FILLED |
| `test_cancel_order` | Order chưa khớp | cancel_order() = True |
| `test_get_account_balance_real` | | cash, buying_power > 0 |
| `test_get_stock_positions_real` | | List đúng với iBoard UI |

**Reconciliation Test**

```python
def test_portfolio_matches_ssi_account():
    """
    So sánh portfolio.json với dữ liệu thật từ SSIBroker.
    Chạy thủ công sau mỗi phiên giao dịch.
    """
    local = load_portfolio()
    real = ssi_broker.get_stock_positions(ACCOUNT)
    for symbol, local_pos in local.positions.items():
        ssi_pos = next(p for p in real if p.symbol == symbol)
        assert local_pos.shares == ssi_pos.qty, f"Mismatch: {symbol}"
```

**✅ Milestone 8 pass khi:**
- SSIDataClient fetch đúng OHLCV (so sánh với iBoard)
- SSIBroker đặt được lệnh thật với 1 cổ phiếu và cancel thành công
- portfolio.json khớp với SSI account sau mỗi phiên

---

### Milestone 9 — Live Trading Gate (Phase 2 → Phase 3)

**Manual verification checklist (bắt buộc trước khi scale lên 500M VND):**

```
□ >= 60 ngày live trading Phase 2 không có lỗi API
□ Lợi nhuận thực tế >= 0% (không lỗ vốn)
□ MDD_real < 150% MDD_backtest (circuit breaker chưa kích hoạt)
□ Tất cả orders đều được reconcile đúng với SSI account
□ Không có order nào bị đặt sai (sai mã, sai khối lượng)
□ Implementation shortfall tracking cho thấy delay cost chấp nhận được
□ Tổng số giao dịch tích lũy >= 60
```

---

## Phase 3 — Full Auto

### Reliability Tests

| Test | Mô tả | Tần suất |
|---|---|---|
| `test_uptime_during_trading_hours` | Monitor process, alert nếu down | Mỗi ngày |
| `test_watchdog_restarts_crashed_bot` | Kill process, đo thời gian restart | Weekly |
| `test_all_orders_have_audit_trail` | 100% orders trong orders table | Daily check |
| `test_no_order_placed_when_circuit_breaker_active` | | Sau mỗi lần circuit breaker kích hoạt |

### Kelly Criterion Validation (khi đủ 300 trades)

```python
def test_kelly_sizing_with_real_stats():
    """Chạy khi có >= 300 trades để validate Kelly Criterion."""
    trades = load_all_trades()
    assert len(trades) >= 300, "Cần 300 trades để Kelly có ý nghĩa thống kê"

    win_rate = calculate_win_rate(trades)
    avg_rr = calculate_avg_rr(trades)
    kelly_f = (win_rate * avg_rr - (1 - win_rate)) / avg_rr
    half_kelly = kelly_f * 0.5

    # Half-Kelly không nên quá aggressive
    assert half_kelly <= 0.20, f"Half-Kelly {half_kelly:.1%} vượt max 20%/position"
    assert half_kelly > 0, "Kelly âm — strategy không có edge!"
```

---

## Coverage Targets

| Component | Unit Test | Integration | Manual E2E |
|---|---|---|---|
| DataSourceProtocol implementations | 90% | ✅ | - |
| MomentumV1 (look-ahead bias) | 100% (critical) | - | - |
| RiskEngine (circuit breaker, sizing) | 100% (critical) | - | - |
| SimulatedBroker (fill logic, phí) | 95% | ✅ | - |
| PortfolioManager (P&L, metrics) | 90% | ✅ | - |
| Backtester | 85% | ✅ | - |
| Scheduler jobs | 80% | - | ✅ |
| Streamlit UI | - | - | ✅ checklist |
| SSIBroker | 70% | ✅ (cần API key) | ✅ |
| E2E paper trading flow | - | - | ✅ scenarios |

## Test Tools

| Công cụ | Dùng cho |
|---|---|
| `pytest` | Unit + integration tests |
| `pytest-mock` / `unittest.mock` | Mock network calls, SSI API |
| `freezegun` | Freeze time cho scheduler tests |
| `pandas.testing` | So sánh DataFrames chính xác |
| Manual checklist (md file) | UI tests, E2E scenarios |
