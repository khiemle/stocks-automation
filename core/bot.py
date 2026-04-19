"""
TradingBot — APScheduler-based bot for VN swing trading.

Communicates with streamlit_app.py via shared files:
  state/signal_queue.json  — signal approval queue (read+write by both)
  data/portfolio.json      — portfolio state (write by bot, read by UI)
  data/trades.db           — trade history (write by bot, read by UI)

Job schedule (Asia/Ho_Chi_Minh):
  15:35  daily_scan_job       — scan all symbols, write PENDING signals
  09:10  order_placement_job  — place APPROVED signals
  14:30  cancel_unfilled_job  — cancel ORDER_PLACED orders still unfilled
  15:10  equity_snapshot_job  — record NAV to DB
  Mon 08:00  weekly_reset_job — reset weekly P&L tracker
  08:30  signal_expiry_job    — expire old PENDING signals
  every 30 min (09:00-15:30)  intraday_monitor_job — stop/trail + watchlist
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

try:
    from core.market_regime import MarketRegime
except Exception:  # pragma: no cover — optional dependency
    MarketRegime = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

_SIGNAL_QUEUE_PATH = Path("state/signal_queue.json")
_TIMEZONE = "Asia/Ho_Chi_Minh"

# intraday monitor active window: 09:00–15:30 (inclusive of start)
_INTRADAY_START_HOUR = 9
_INTRADAY_END_HOUR = 15
_INTRADAY_END_MINUTE = 30
_SKIP_TRADING_HOURS_CHECK = False  # set True in tests to bypass time-of-day guard


# ---------------------------------------------------------------------------
# Signal data model
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    symbol: str
    action: str          # "BUY" | "SELL"
    score: float
    engine: str
    source: str          # "EOD" | "INTRADAY"
    created_at: str      # ISO datetime (local)
    stop_loss: float
    take_profit: float
    indicators: dict = field(default_factory=dict)
    status: str = "PENDING"  # PENDING|APPROVED|REJECTED|EXPIRED|ORDER_PLACED|FILLED
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# TradingBot
# ---------------------------------------------------------------------------

class TradingBot:
    def __init__(
        self,
        config: dict,
        data_manager,
        signal_engines: list,
        broker,
        portfolio_path: Optional[Path] = None,
        db_path: Optional[Path] = None,
        signal_queue_path: Optional[Path] = None,
    ) -> None:
        self._config = config
        self._dm = data_manager
        self._engines = signal_engines
        self._broker = broker

        if signal_queue_path is not None:
            # Override module-level constant for this instance's persistence
            self._signal_queue_path = Path(signal_queue_path)
        else:
            self._signal_queue_path = _SIGNAL_QUEUE_PATH

        from core.portfolio_manager import PortfolioManager
        from core.risk_engine import RiskEngine

        initial_cash = config["capital"]["initial"]
        self._portfolio = PortfolioManager(
            initial_cash=initial_cash,
            db_path=db_path,
            portfolio_path=portfolio_path,
        )
        self._risk = RiskEngine(backtest_mdd=0.20, capital=initial_cash)
        self._queue: List[Signal] = self._load_queue()

        self._scheduler = None
        self.recover_state()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        sch = self._config.get("scheduler", {})
        self._scheduler = BackgroundScheduler(timezone=_TIMEZONE)

        daily_time = sch.get("daily_scan_time", "15:35").split(":")
        self._scheduler.add_job(
            self.daily_scan_job, CronTrigger(
                hour=int(daily_time[0]), minute=int(daily_time[1]),
                timezone=_TIMEZONE,
            ), id="daily_scan", replace_existing=True,
        )

        order_time = sch.get("order_placement_time", "09:10").split(":")
        self._scheduler.add_job(
            self.order_placement_job, CronTrigger(
                hour=int(order_time[0]), minute=int(order_time[1]),
                timezone=_TIMEZONE,
            ), id="order_placement", replace_existing=True,
        )

        cancel_time = sch.get("cancel_unfilled_time", "14:30").split(":")
        self._scheduler.add_job(
            self.cancel_unfilled_job, CronTrigger(
                hour=int(cancel_time[0]), minute=int(cancel_time[1]),
                timezone=_TIMEZONE,
            ), id="cancel_unfilled", replace_existing=True,
        )

        equity_time = sch.get("equity_snapshot_time", "15:10").split(":")
        self._scheduler.add_job(
            self.equity_snapshot_job, CronTrigger(
                hour=int(equity_time[0]), minute=int(equity_time[1]),
                timezone=_TIMEZONE,
            ), id="equity_snapshot", replace_existing=True,
        )

        weekly_day = sch.get("weekly_reset_day", "monday")
        weekly_time = sch.get("weekly_reset_time", "08:00").split(":")
        self._scheduler.add_job(
            self.weekly_reset_job, CronTrigger(
                day_of_week=weekly_day[:3],
                hour=int(weekly_time[0]), minute=int(weekly_time[1]),
                timezone=_TIMEZONE,
            ), id="weekly_reset", replace_existing=True,
        )

        expiry_time = sch.get("signal_expiry_time", "08:30").split(":")
        self._scheduler.add_job(
            self.signal_expiry_job, CronTrigger(
                hour=int(expiry_time[0]), minute=int(expiry_time[1]),
                timezone=_TIMEZONE,
            ), id="signal_expiry", replace_existing=True,
        )

        interval_min = sch.get("intraday_interval_minutes", 30)
        self._scheduler.add_job(
            self.intraday_monitor_job,
            "interval",
            minutes=interval_min,
            id="intraday_monitor",
            replace_existing=True,
        )

        self._scheduler.start()
        logger.info("TradingBot started — mode=%s", self._config.get("mode", "PAPER"))

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("TradingBot stopped")

    # ------------------------------------------------------------------
    # State recovery (called on start)
    # ------------------------------------------------------------------

    def recover_state(self) -> None:
        """Sync ORDER_PLACED signals: check actual broker status."""
        placed = [s for s in self._queue if s.status == "ORDER_PLACED"]
        for sig in placed:
            try:
                status = self._broker.get_order_status(sig.id)
                if status.status == "FILLED":
                    sig.status = "FILLED"
                    logger.info("recover_state: %s FILLED", sig.symbol)
            except Exception as exc:
                logger.warning("recover_state: get_order_status(%s) failed: %s", sig.id, exc)
        if placed:
            self._save_queue()

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def daily_scan_job(self) -> None:
        """15:35 — scan all symbols, write PENDING EOD signals."""
        logger.info("daily_scan_job: starting")
        symbols = list(dict.fromkeys(
            self._dm.get_universe("HOSE") + self._dm.get_universe("HNX")
        ))

        # Macro regime context
        try:
            regime = MarketRegime()
            macro_ctx = regime.context(pd.Timestamp.today().normalize())
        except Exception as exc:
            logger.warning("MarketRegime unavailable: %s", exc)
            macro_ctx = None

        portfolio_symbols = list(self._portfolio.positions.keys())
        new_signals: List[Signal] = []

        for sym in symbols:
            try:
                df = self._dm.get_ohlcv(sym, days=300)
                for engine in self._engines:
                    eligible, reason = engine.is_eligible(
                        df, sym, portfolio_symbols, t2_lock_symbols=None,
                    )
                    if not eligible:
                        continue
                    result = engine.evaluate(df, foreign_flow=None, market_context=macro_ctx)
                    if result.action == "BUY":
                        atr_v = float(result.indicators.get("atr", 0)) or float(df["close"].iloc[-1]) * 0.02
                        close_v = float(result.indicators.get("close", df["close"].iloc[-1]))
                        from core.risk_engine import RiskEngine
                        stop = close_v - RiskEngine.ATR_STOP_MULT * atr_v
                        tp = close_v + RiskEngine.ATR_TP_MULT * atr_v
                        new_signals.append(Signal(
                            symbol=sym,
                            action="BUY",
                            score=result.score,
                            engine=engine.name,
                            source="EOD",
                            created_at=datetime.now().isoformat(timespec="seconds"),
                            stop_loss=stop,
                            take_profit=tp,
                            indicators=result.indicators,
                        ))
                        logger.info("BUY signal: %s score=%.3f", sym, result.score)
            except FileNotFoundError:
                pass
            except Exception as exc:
                logger.warning("daily_scan_job error for %s: %s", sym, exc)

        # Log to DB
        self._log_scan_to_db(new_signals)

        # Merge into queue (deduplicate: drop any existing PENDING for same symbol)
        self._queue = [
            s for s in self._queue
            if not (s.symbol in {sig.symbol for sig in new_signals} and s.status == "PENDING")
        ]
        self._queue.extend(new_signals)
        self._save_queue()
        logger.info("daily_scan_job: %d new BUY signals", len(new_signals))

    def intraday_monitor_job(self) -> None:
        """Every 30 min — check stops/trailing for positions + watchlist scan."""
        if not _SKIP_TRADING_HOURS_CHECK:
            now = datetime.now()
            if not (
                now.hour >= _INTRADAY_START_HOUR
                and (now.hour < _INTRADAY_END_HOUR
                     or (now.hour == _INTRADAY_END_HOUR and now.minute <= _INTRADAY_END_MINUTE))
            ):
                return  # outside trading hours

        from core.risk_engine import RiskEngine

        positions = self._portfolio.positions
        watchlist: list[str] = self._config.get("watchlist", [])
        symbols_to_fetch = list(positions.keys()) + watchlist

        if not symbols_to_fetch:
            return

        prices: dict[str, float | None] = {}
        try:
            prices = self._dm.data_source.get_intraday_prices_batch(symbols_to_fetch)
        except Exception as exc:
            logger.warning("intraday_monitor: price fetch failed: %s", exc)
            return

        state_changed = False

        # Portfolio: stop / trailing
        for sym, pos in list(positions.items()):
            price = prices.get(sym)
            if price is None or price <= 0:
                continue

            # Check stop first
            if price <= pos.stop_loss:
                logger.info("intraday_monitor: STOP hit for %s at %.0f", sym, price)
                self._place_exit_order(sym, pos, price, reason="STOP")
                state_changed = True
                continue

            # Fixed TP check (fallback — trailing supersedes in practice)
            if pos.take_profit > 0 and price >= pos.take_profit:
                logger.info("intraday_monitor: TP hit for %s at %.0f", sym, price)
                self._place_exit_order(sym, pos, price, reason="TP")
                state_changed = True
                continue

            # Trailing stop: activate when price >= entry + ATR_TRAIL_TRIGGER × entry_atr
            if pos.entry_atr > 0:
                trigger = pos.avg_price + RiskEngine.ATR_TRAIL_TRIGGER * pos.entry_atr
                if not pos.trail_active and price >= trigger:
                    pos.trail_active = True
                    state_changed = True
                if pos.trail_active:
                    new_stop = price - RiskEngine.ATR_TRAIL_MULT * pos.entry_atr
                    if new_stop > pos.stop_loss:
                        self._portfolio.update_stop(sym, new_stop)
                        state_changed = True
                        logger.debug("intraday_monitor: trail stop %s → %.0f", sym, new_stop)

        # Watchlist: generate INTRADAY signals
        min_score = self._config.get("signal", {}).get("min_score", 0.55)
        existing_syms = {s.symbol for s in self._queue if s.status == "PENDING"}
        portfolio_symbols = list(positions.keys())

        for sym in watchlist:
            if sym in portfolio_symbols or sym in existing_syms:
                continue
            try:
                df = self._dm.get_ohlcv(sym, days=300)
                for engine in self._engines:
                    result = engine.evaluate(df, foreign_flow=None)
                    if result.score >= min_score and result.action == "BUY":
                        atr_v = float(result.indicators.get("atr", 0)) or float(df["close"].iloc[-1]) * 0.02
                        close_v = float(result.indicators.get("close", df["close"].iloc[-1]))
                        stop = close_v - RiskEngine.ATR_STOP_MULT * atr_v
                        tp = close_v + RiskEngine.ATR_TP_MULT * atr_v
                        intraday_sig = Signal(
                            symbol=sym,
                            action="BUY",
                            score=result.score,
                            engine=engine.name,
                            source="INTRADAY",
                            created_at=datetime.now().isoformat(timespec="seconds"),
                            stop_loss=stop,
                            take_profit=tp,
                            indicators=result.indicators,
                        )
                        self._queue.append(intraday_sig)
                        state_changed = True
                        logger.info("INTRADAY signal: %s score=%.3f", sym, result.score)
            except Exception as exc:
                logger.warning("intraday_monitor watchlist error %s: %s", sym, exc)

        if state_changed:
            self._portfolio.save_state()
            self._save_queue()

    def order_placement_job(self) -> None:
        """09:10 — place APPROVED signals as orders."""
        approved = [s for s in self._queue if s.status == "APPROVED"]
        if not approved:
            return

        portfolio_symbols = list(self._portfolio.positions.keys())
        max_pos = self._config["capital"].get("max_positions", 5)

        for sig in approved:
            if len(portfolio_symbols) >= max_pos:
                logger.info("order_placement: max_positions reached, skipping %s", sig.symbol)
                break
            if sig.symbol in portfolio_symbols:
                sig.status = "REJECTED"
                continue
            try:
                result = self._broker.place_order(
                    symbol=sig.symbol,
                    side="B",
                    quantity=self._compute_qty(sig),
                    order_type="ATO",
                    price=None,
                    account="paper",
                )
                if result.status in ("PLACED", "SIMULATED"):
                    sig.status = "ORDER_PLACED"
                    sig.id = result.order_id
                    logger.info("order_placement: %s placed order_id=%s", sig.symbol, sig.id)
                else:
                    sig.status = "REJECTED"
                    logger.warning("order_placement: %s rejected — %s", sig.symbol, result.message)
            except Exception as exc:
                logger.error("order_placement: %s exception: %s", sig.symbol, exc)

        self._save_queue()

    def cancel_unfilled_job(self) -> None:
        """14:30 — cancel orders still in ORDER_PLACED status."""
        placed = [s for s in self._queue if s.status == "ORDER_PLACED"]
        for sig in placed:
            try:
                self._broker.cancel_order(sig.id, account="paper")
                sig.status = "REJECTED"
                logger.info("cancel_unfilled: %s cancelled", sig.symbol)
            except Exception as exc:
                logger.warning("cancel_unfilled: %s failed: %s", sig.symbol, exc)
        if placed:
            self._save_queue()

    def equity_snapshot_job(self) -> None:
        """15:10 — record daily NAV to equity_history table."""
        positions = self._portfolio.positions
        if not positions:
            return
        try:
            prices = self._dm.data_source.get_intraday_prices_batch(list(positions.keys()))
            prices_clean = {k: v for k, v in prices.items() if v is not None}
            self._portfolio.record_equity_snapshot(prices_clean)
        except Exception as exc:
            logger.warning("equity_snapshot_job failed: %s", exc)

    def weekly_reset_job(self) -> None:
        """Monday 08:00 — reset weekly P&L baseline."""
        positions = self._portfolio.positions
        prices: dict[str, float] = {}
        try:
            prices = {k: v for k, v in
                      self._dm.data_source.get_intraday_prices_batch(list(positions.keys())).items()
                      if v is not None}
        except Exception:
            pass
        equity = self._portfolio.get_equity(prices)
        self._risk.reset_week(equity)
        logger.info("weekly_reset_job: week start equity=%.0f", equity)

    def signal_expiry_job(self) -> None:
        """08:30 — expire PENDING signals from previous days."""
        today = date.today().isoformat()
        expired = 0
        for sig in self._queue:
            if sig.status == "PENDING" and not sig.created_at.startswith(today):
                sig.status = "EXPIRED"
                expired += 1
        if expired:
            self._save_queue()
            logger.info("signal_expiry_job: %d signals expired", expired)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _place_exit_order(self, symbol: str, pos, price: float, reason: str) -> None:
        try:
            result = self._broker.place_order(
                symbol=symbol,
                side="S",
                quantity=pos.qty,
                order_type="ATO",
                price=None,
                account="paper",
            )
            if result.status in ("PLACED", "SIMULATED"):
                exit_date = date.today().isoformat()
                self._portfolio.close_position(symbol, price, exit_date)
                self._portfolio.save_state()
                logger.info("_place_exit_order: %s %s at %.0f", reason, symbol, price)
        except Exception as exc:
            logger.error("_place_exit_order %s failed: %s", symbol, exc)

    def _compute_qty(self, sig: Signal) -> int:
        from core.risk_engine import RiskEngine
        cash = self._portfolio.cash
        atr_v = sig.indicators.get("atr", 0) or 0
        close_v = sig.indicators.get("close", 0) or 0
        if close_v <= 0:
            return 0
        atr_v = atr_v if atr_v > 0 else close_v * 0.02
        stop_dist = RiskEngine.ATR_STOP_MULT * atr_v
        if stop_dist <= 0:
            return 0
        risk_budget = cash * self._risk.RISK_PCT
        max_by_cap = cash * self._risk.MAX_POSITION_PCT / close_v
        raw = min(risk_budget / stop_dist, max_by_cap)
        return int(raw // 100 * 100)

    def _log_scan_to_db(self, signals: List[Signal]) -> None:
        import sqlite3
        db = Path("data/trades.db")
        if not db.exists():
            return
        scanned_at = datetime.now().isoformat(timespec="seconds")
        try:
            with sqlite3.connect(db) as conn:
                conn.executemany(
                    "INSERT INTO scan_logs(scanned_at,symbol,action,score,regime,engine) VALUES (?,?,?,?,?,?)",
                    [(scanned_at, s.symbol, s.action, s.score,
                      s.indicators.get("regime", ""), s.engine)
                     for s in signals],
                )
        except Exception as exc:
            logger.warning("_log_scan_to_db failed: %s", exc)

    # ------------------------------------------------------------------
    # Queue persistence
    # ------------------------------------------------------------------

    def _save_queue(self) -> None:
        _SIGNAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SIGNAL_QUEUE_PATH.write_text(
            json.dumps([asdict(s) for s in self._queue], indent=2)
        )

    def _load_queue(self) -> List[Signal]:
        if not _SIGNAL_QUEUE_PATH.exists():
            return []
        try:
            raw = json.loads(_SIGNAL_QUEUE_PATH.read_text())
            return [Signal(**item) for item in raw]
        except Exception as exc:
            logger.warning("_load_queue failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Properties (for testing / UI inspection)
    # ------------------------------------------------------------------

    @property
    def queue(self) -> List[Signal]:
        return list(self._queue)

    @property
    def portfolio(self):
        return self._portfolio

    @property
    def scheduler(self):
        return self._scheduler
