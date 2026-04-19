# VN Swing Trading — Algorithm Source of Truth

> **Đây là tài liệu trung tâm về thuật toán đang áp dụng cho hệ thống.**
> Mọi thay đổi về signal, risk, execution, hoặc backtest methodology PHẢI cập nhật file này cùng lúc với code theo [Commit Protocol](#5-commit-protocol) ở cuối file.
>
> **Last updated**: 2026-04-19 · **Commit**: `d71eff7` · **Baseline algo version**: `MomentumV1 v1.0`

---

## Table of Contents

1. [Current Algorithm Spec](#1-current-algorithm-spec)
2. [Baseline Performance (VN30 5-year)](#2-baseline-performance)
3. [Improvement Roadmap](#3-improvement-roadmap)
4. [Change Log](#4-change-log)
5. [Commit Protocol](#5-commit-protocol)

---

## 1. Current Algorithm Spec

### 1.1 Signal Engine — `MomentumV1 v1.0`

File: `signals/momentum_v1.py`

#### Scoring (base weights sum = 1.0)

| Component | Weight | Formula | Range |
|-----------|-------:|---------|:-----:|
| MA divergence | 0.25 | `clamp((ema20 - ema60) / ema60 × 20)` | [-1, +1] |
| MACD | 0.25 | `sign(macd)×0.5 + clamp(hist / (close × 0.0003))×0.5` | [-1, +1] |
| RSI14 | 0.20 | `(rsi - 50) / 20` · taper from +1 at 70 down to -1 at 75 | [-1, +1] |
| ADX14 | 0.15 | `(DI+ - DI-)/(DI+ + DI-) × min(adx/25, 1)` | [-1, +1] |
| Volume | 0.10 | `vol / vol_MA20 - 1` | [-1, +1] |
| Foreign flow | 0.05 | `avg5(net_value)` scaled · weight → 0 if data missing | [-1, +1] |

Composite score = weighted sum, normalized after regime adjustment.

#### Regime Detection

| Regime | Condition | Effect |
|--------|-----------|--------|
| VOLATILE | `ATR/close > 3%` | confidence × 0.7 |
| SIDEWAYS | `ADX ≤ 25` (and not VOLATILE) | MA weight × 0.7, confidence × 0.85 |
| TRENDING | `ADX > 25` (and not VOLATILE) | no adjustment |

#### Hard Gates (block BUY)

- `RSI14 > 75` → score clamped to `_BUY_THRESHOLD - 0.01`
- `close < EMA200` → score clamped to `_BUY_THRESHOLD - 0.01` *(trend filter — skipped if < 200 bars of history)*

#### Thresholds

| Action | Condition |
|--------|-----------|
| BUY | score > `+0.55` |
| SELL | score < `-0.55` |
| HOLD | otherwise |

#### Eligibility (`MomentumV1.is_eligible`)

- `vol_MA20 ≥ 100,000` shares
- `close ≥ 5,000` VND
- symbol not in current portfolio
- symbol not in T+2 lock list

### 1.2 Risk Engine

File: `core/risk_engine.py`

| Parameter | Value | Usage |
|-----------|------:|-------|
| `ATR_STOP_MULT` | 1.5 | `stop = entry − 1.5 × ATR14` |
| `ATR_TP_MULT` | 4.5 | `TP = entry + 4.5 × ATR14` (R:R ≈ 1:3) |
| `RISK_PCT` | 2% | per-trade risk vs current cash |
| `MAX_POSITION_PCT` | 20% | half-Kelly cap per position |
| `MAX_ADV_PCT` | 5% | max order size vs 20-day ADV |
| Weekly warn | -1.5% | soft limit — warning |
| Weekly stop | -3.0% | hard limit — pause new entries |
| MDD circuit breaker | 150% × backtest MDD | latch STOP ALL |
| HOSE price band | ±7% | stop must be within band |
| HNX price band | ±10% | stop must be within band |

Position sizing: `shares = min(risk_budget / stop_dist, position_cap / close, adv_cap)`, then round down to VN lot size (100 shares).

### 1.3 Execution — `SimulatedBroker` (Phase 1)

File: `brokers/simulated_broker.py` · **Source of truth for `_COMMISSION_RATE` and `_SLIPPAGE_RATE`.**

| Parameter | Value |
|-----------|------:|
| Commission | 0.15% per side |
| Slippage | 0.10% per side |
| Fill timing | T+1 open price |
| Settlement | T+2 enforced via `pd.bdate_range` (≥ 2 business days buy→sell) |

### 1.4 Backtester Methodology

File: `core/backtester.py`

- **Warmup**: `_WARMUP_BARS = 252` — signal generation skipped until bar 252 so EMA200 is calibrated on pre-window history.
- **Data load**: `_load(symbol, years)` returns `df.tail(years × 365 + 252)` bars.
- **Walk-forward**: 70/30 in-sample/out-of-sample split. OOS slice prepends `_WARMUP_BARS` bars from the IS tail so EMA200 remains calibrated in OOS.
- **Event flow per bar T**:
  1. At close(T) → evaluate signal on `df[:T+1]` (no look-ahead)
  2. Pending BUY/SELL filled at open(T+1) via `SimulatedBroker.process_next_bar`
  3. Stop/TP checked on high/low(T+1 onwards), but only when T+2 elapsed from entry
  4. Re-entry blocked on stop-out bar (no immediate BUY after forced exit)
- **Benchmark**: per-symbol buy-hold return (buy at warmup close, sell at last close, round-trip costs included). VN-Index not available on yfinance.

---

## 2. Baseline Performance

**Window**: 2021-04-19 → 2026-04-17 (5 years, through 2022 crash + 2023-2025 recovery)
**Universe**: VN30 (31 symbols — includes one extra vs canonical 30)
**Data**: `data/backtest_vn30_2021-2026.csv`
**Algo version**: `MomentumV1 v1.0` (EMA200 filter active)

### 2.1 Aggregate Metrics

| Metric | Value | Target | Status |
|--------|------:|-------:|:------:|
| Median total return | +0.15% | > 75% (5yr ≈ 15%/yr) | ❌ |
| Mean total return | +1.79% | > 75% | ❌ |
| Median Sharpe | 0.025 | > 1.0 | ❌ |
| Median MDD | 5.24% | < 15% | ✅ |
| Median win rate | 33.33% | > 52% | ❌ |
| Median profit factor | 0.98 | > 1.5 | ❌ |
| Median alpha vs B&H | -33.00% | > 0 | ❌ |
| Symbols with +alpha | 7 / 31 | > 15 / 31 | ❌ |
| Total trades | 478 | ≥ 300 | ✅ |

### 2.2 Per-Symbol Highlights

**Best alpha** (strategy added value):
| Symbol | Strategy | B&H | Alpha |
|--------|---------:|----:|------:|
| PDR | +2.97% | -73.62% | **+76.59%** |
| SAB | -10.37% | -35.52% | +25.15% |
| BCM | +0.04% | -21.70% | +21.73% |
| TPB | +2.34% | -10.27% | +12.60% |
| SSI | +12.30% | +0.57% | +11.73% |

**Worst alpha** (strategy left money on the table):
| Symbol | Strategy | B&H | Alpha |
|--------|---------:|----:|------:|
| VIC | +19.86% | +383.16% | **-363.30%** |
| VHM | +12.61% | +269.25% | -256.64% |
| HDB | -4.37% | +147.83% | -152.20% |
| STB | +10.27% | +120.19% | -109.92% |
| MBB | -0.90% | +92.80% | -93.71% |

### 2.3 Key Observations

1. **EMA200 filter works as defense** — 5/7 symbols with positive alpha had negative B&H (PDR, SAB, BCM, TPB, PLX). Filter successfully avoids downtrending stocks.
2. **Strategy cannot hold winners** — VIC rose 383% but strategy captured only 19.86%. R:R 1:3 with fixed TP causes early exits on strong trends.
3. **Win rate 33% with R:R 1:3** gives breakeven EV but no margin — needs either +5-7pp win rate or asymmetric exits.
4. **Trade frequency is low** (~15 trades/symbol/5yr = 3/year) — BUY_THRESHOLD 0.55 + EMA200 gate is very restrictive. Most trades come from the same few symbols.
5. **Consistent across symbols**: Sharpe clusters near 0, MDD all < 15% — low-activity, low-drawdown, low-return.

---

## 3. Improvement Roadmap

Status: `[ ]` todo · `[~]` in progress · `[x]` done (with commit SHA + measured impact)

### 3.1 Market-Level Filters

- [ ] **VN30 macro regime filter** — compute equal-weight VN30 basket EMA50; block new BUY when basket < basket EMA50
  - **Rationale**: 70% correlation between VN30 stocks and the basket. Fighting macro = large losses in bear markets (2022).
  - **Expected impact**: Reduce false BUY during bear periods; improve MDD and win rate.
  - **Success**: MDD ≤ 4%, win rate ≥ 38%
- [ ] **Relative strength vs VN30 basket** — only BUY when symbol return(20d) > basket return(20d)
  - **Rationale**: Swing momentum requires leadership vs the market. VIC/VHM-type runs come from stocks leading the basket.
  - **Expected impact**: Concentrate on leaders, avoid laggards.
  - **Success**: Median alpha > -15% (vs current -33%)

### 3.2 Entry Refinement

- [ ] **Volume breakout confirmation** — require `vol > 150% × vol_MA20` on signal bar
  - **Rationale**: Current weight 0.10 allows BUY on weak volume. Momentum without volume = chop.
  - **Success**: Win rate ≥ 40%
- [ ] **MACD zero-line requirement** — add hard gate: MACD line must be > 0 to BUY (not just > signal)
  - **Rationale**: Current gate lets BUY trigger when both MACD & signal are negative (still downtrend).
  - **Success**: Win rate ≥ 36%
- [ ] **Avoid late-day BUY** (live scan only) — scan at 15:35, but tag signals > 14:45 as "late" and require score > 0.65 instead of 0.55
  - **Rationale**: Late-session rallies tend to gap down next morning.
  - **Success**: Avg gap loss reduced
- [ ] **Remove EMA200 for small-cap** — EMA200 filter too strict for recovery plays; skip filter when symbol is in recovery regime (price > 52w low × 1.3)

### 3.3 Exit Refinement (biggest expected impact)

- [ ] **Trailing stop after +1R** — once unrealized gain > 1R (= 1.5×ATR), trail stop at `high - 2×ATR`; remove fixed TP
  - **Rationale**: VIC case — algo exited at +4.5R, missing next 40R run. Trailing lets winners run.
  - **Expected impact**: Huge (biggest lever in backtest).
  - **Success**: Profit factor ≥ 1.5, avg win ≥ 2× current
- [ ] **Regime-adaptive TP** — TRENDING: keep ATR×4.5 or trailing; SIDEWAYS: tighten to ATR×2; VOLATILE: tighten to ATR×1.5
  - **Rationale**: Sideways markets give back gains quickly — lock profit faster.
  - **Success**: Win rate in SIDEWAYS ≥ 45%
- [ ] **Breakeven stop after +1R** — move stop to entry when +1R reached (loss protection)
  - **Rationale**: Small change, prevents winning-to-loss flips.
  - **Success**: Avg loss reduced 20%

### 3.4 Position Sizing

- [ ] **Kelly fraction from 30-trade rolling** — after 30 trades, use `half-Kelly = 0.5 × (W - (1-W)/R)` capped at 2%
  - **Rationale**: Current fixed 2% doesn't adapt to observed edge.
  - **Success**: CAGR +2% without MDD > +2%
- [ ] **Volatility-adjusted risk** — VOLATILE regime: reduce `RISK_PCT` to 1% (from 2%)
  - **Rationale**: Volatile = stops hit more often; reduce size to protect capital.
  - **Success**: MDD in VOLATILE periods reduced ≥ 3pp

### 3.5 Portfolio-Level

- [ ] **Sector concentration limit** — max 2 open positions per sector (banks, real estate, steel, retail)
  - **Rationale**: VN30 has 6-7 banks + 4-5 real-estate stocks. High intra-sector correlation.
  - **Success**: Correlation-adjusted Sharpe ≥ 0.5
- [ ] **Correlation-based position filter** — reject new BUY if `corr(20d, existing_positions) > 0.7`
  - **Rationale**: Statistical version of sector filter.
  - **Success**: Portfolio equity curve smoother

### 3.6 Signal Engine Extensions (Phase 2+)

- [ ] **Foreign flow from SSI** — once Phase 2 has SSI integration, bump foreign-flow weight from 0.05 → 0.15
  - **Rationale**: Foreign flow is a strong leading indicator in VN; 0.05 is too low.
  - **Success**: Win rate ≥ 45%
- [ ] **Intraday volume profile** — mid-session (≥ 10:30) check cumulative vol > 50% of projected daily vol before entering
  - **Rationale**: Confirms momentum earlier in session.

### 3.7 Model Validation

- [ ] **2022 crash stress test** — backtest only Q2-Q3 2022 window
  - **Success**: MDD in that period < 10% (vs ~15% buy-hold)
- [ ] **Parameter sensitivity grid** — sweep BUY_THRESHOLD ∈ {0.45, 0.50, 0.55, 0.60, 0.65} × ATR_TP_MULT ∈ {2, 3, 4.5, 6, trailing}
  - **Success**: Identify flat plateau (robust) vs sharp peak (overfit)
- [ ] **Walk-forward re-validation** — after Top-3 improvements implemented, re-run `run_all(walk_forward=True)`
  - **Success**: IS/OOS Sharpe difference < 0.3

### 3.8 Priority Order (suggested)

Based on **expected impact × ease of implementation**:

1. 🔥 **Trailing stop** (3.3) — biggest lever; VIC/VHM case shows 10x opportunity
2. 🔥 **Relative strength vs VN30 basket** (3.1) — focuses capital on leaders
3. 🔥 **Regime-adaptive TP** (3.3) — easy to implement, clear rationale
4. **VN30 macro filter** (3.1) — defensive improvement
5. **Volume breakout confirmation** (3.2) — quality filter
6. **Sector concentration limit** (3.5) — reduce hidden correlation

---

## 4. Change Log

| Date | Change | Commit | Notes |
|------|--------|--------|-------|
| 2026-04-19 | **Initial SSoT doc + VN30 5-year baseline** | `d71eff7` | 31 symbols, median alpha -33% |
| 2026-04-19 | Added buy-hold benchmark + alpha to metrics | `24b6cd2` | BacktestMetrics.benchmark_return, alpha |
| 2026-04-19 | Fixed 4 consistency issues | `705d3dc` | Single source of truth for commission/slippage |
| 2026-04-19 | Live scan loads 300 bars | `228b62d` | EMA200 filter active in scan (was NaN) |
| 2026-04-19 | EMA200 warmup 252 bars in backtest | `2709e8e` | Filter calibrated on pre-window data |
| 2026-04-19 | EMA200 trend filter added | `7deba8e` | Block BUY when `close < EMA200` |
| 2026-04-19 | T+2 enforced for stop/TP exits | `233f679` | Previously bypassed via intraday exit |
| 2026-04-19 | T+2 enforced with `sim_date` | `c6e53e1` | Previously used `date.today()` |
| 2026-04-19 | Backtester rapid-fire BUY bugs fixed | `9750f37` | Entry-bar guard, qty>0 guard, pending guard |
| 2026-04-19 | Week 5 initial implementation | `d9f132d` | SimulatedBroker + Backtester + 13 tests |

---

## 5. Commit Protocol

**Every time** you change the algorithm (signal weights/thresholds/filters, risk params, execution logic, backtest methodology):

1. **Update code** in `signals/`, `core/`, `brokers/`
2. **Update this doc** — section 1 (algo spec) with the new values
3. **Update `system-design.md`** if architecture shifts (e.g. new module, interface change)
4. **Update `product-spec.md`** if strategy philosophy shifts (e.g. Kelly sizing policy, new risk budget)
5. **Append section 4 (Change Log)** with date, commit SHA, one-line description
6. **If closing a roadmap item** (section 3):
   - Change `[ ]` → `[x]`
   - Append commit SHA and measured success metric
7. **Re-run VN30 backtest** — `python scripts/backtest_vn30.py`
   - If median alpha moved > 5pp, update section 2.1 + add observation to 2.3
8. **One commit per algorithm change** (Workflow Rule #1 in CLAUDE.md)

If multiple independent improvements are needed, do them as separate tickets and separate commits — don't bundle.

### Change template

When editing section 1, use this comment style if removing/replacing a rule:

```markdown
<!-- REMOVED 2026-04-22 commit abc1234: RSI>75 gate replaced with soft decay to -1.0 at RSI=80 -->
```

Never silently rewrite section 1 — leave the removed rule as a comment for audit.
