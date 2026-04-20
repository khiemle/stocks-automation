"""
trading_bot.py — Main bot process.
Runs independently from streamlit_app.py.
Communicates via shared JSON + SQLite files.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def load_config() -> dict:
    path = Path("config/config.json")
    with path.open() as f:
        return json.load(f)


def build_bot(config: dict):
    from data_sources.yfinance_client import YFinanceClient
    from data_sources.ssi_data_client import SSIDataClient
    from brokers.simulated_broker import SimulatedBroker
    from signals.registry import ENGINE_REGISTRY
    from core.data_manager import DataManager

    data_source_cls = {"YFINANCE": YFinanceClient, "SSI": SSIDataClient}[
        config["data_source"]
    ]
    data_source = data_source_cls()
    data_manager = DataManager(data_source)

    engines = [
        ENGINE_REGISTRY[e["name"]]()
        for e in config["signal_engines"]
        if e["enabled"]
    ]

    broker_cls = {"SimulatedBroker": SimulatedBroker}[config["broker"]]
    broker = broker_cls()

    from core.bot import TradingBot
    return TradingBot(config=config, data_manager=data_manager, signal_engines=engines, broker=broker)


def cmd_start(args):
    config = load_config()
    bot = build_bot(config)
    bot.start()


def cmd_place_orders(args):
    """Trigger order_placement_job immediately — place all APPROVED signals now."""
    config = load_config()
    bot = build_bot(config)
    approved_before = [s for s in bot.queue if s.status == "APPROVED"]
    if not approved_before:
        print("Không có signal nào ở trạng thái APPROVED trong queue.")
        return
    print(f"Tìm thấy {len(approved_before)} APPROVED signal(s): {[s.symbol for s in approved_before]}")
    bot.order_placement_job()
    placed = [s for s in bot.queue if s.status == "ORDER_PLACED"]
    rejected = [s for s in bot.queue if s.status == "REJECTED" and s.symbol in {a.symbol for a in approved_before}]
    print(f"\nKết quả:")
    for s in placed:
        print(f"  ✅ ORDER_PLACED  {s.symbol}  order_id={s.id}")
    for s in rejected:
        print(f"  ❌ REJECTED      {s.symbol}")


def cmd_scan_signals(args):
    """Run daily_scan_job immediately: scan → write signal_queue → Telegram notify."""
    config = load_config()
    bot = build_bot(config)
    print("Running daily scan (reads local Parquet data)...")
    bot.daily_scan_job()
    queue = bot.queue
    buys = [s for s in queue if s.action == "BUY" and s.status == "PENDING"]
    print(f"\nDone. {len(buys)} BUY signal(s) written to state/signal_queue.json")
    for sig in sorted(buys, key=lambda s: -s.score):
        print(f"  {sig.symbol:6s}  score={sig.score:+.3f}  stop={sig.stop_loss:,.0f}  tp={sig.take_profit:,.0f}")


def cmd_init_data(args):
    config = load_config()
    from data_sources.yfinance_client import YFinanceClient
    from data_sources.ssi_data_client import SSIDataClient
    from core.data_manager import DataManager

    data_source_cls = {"YFINANCE": YFinanceClient, "SSI": SSIDataClient}[
        config["data_source"]
    ]
    dm = DataManager(data_source_cls())
    dm.init_data(years=args.years)


def cmd_scan(args):
    config = load_config()
    from data_sources.yfinance_client import YFinanceClient
    from data_sources.ssi_data_client import SSIDataClient
    from core.data_manager import DataManager
    from core.market_regime import MarketRegime
    from signals.momentum_v1 import MomentumV1
    import pandas as pd

    data_source_cls = {"YFINANCE": YFinanceClient, "SSI": SSIDataClient}[
        config["data_source"]
    ]
    dm = DataManager(data_source_cls())
    engine = MomentumV1()

    # Macro regime — compute once at scan time, use latest available date
    try:
        regime = MarketRegime()
        macro_ctx = regime.context(pd.Timestamp.today().normalize())
    except Exception as exc:
        print(f"[WARN] MarketRegime unavailable: {exc}. Macro filter OFF.")
        macro_ctx = None

    symbols = [args.symbol] if args.symbol else list(dict.fromkeys(
        dm.get_universe("HOSE") + dm.get_universe("HNX")
    ))

    results = []
    for sym in symbols:
        try:
            df = dm.get_ohlcv(sym, days=300)
            result = engine.evaluate(df, foreign_flow=None,
                                     market_context=macro_ctx)
            results.append((sym, result))
            if args.symbol:
                ind = result.indicators
                print(f"Symbol  : {sym}")
                print(f"Action  : {result.action}  (score={result.score:+.3f}, confidence={result.confidence:.2f})")
                print(f"Regime  : {result.regime}")
                ema200 = ind.get("ema200")
                ema200_str = f"{ema200:.0f}" if ema200 else "n/a (< 200 bars)"
                print(f"EMA20/60/200: {ind['ema20']:.0f} / {ind['ema60']:.0f} / {ema200_str}")
                above = "✓ above EMA200" if ema200 and float(ind.get("close", 0)) > ema200 else ("✗ below EMA200 — BUY blocked" if ema200 else "")
                print(f"MACD    : {ind['macd']:.1f} (signal {ind['macd_signal']:.1f})")
                print(f"RSI14   : {ind['rsi']:.1f}")
                print(f"ADX14   : {ind['adx']:.1f}  (+DI {ind['adx_pos']:.1f} / -DI {ind['adx_neg']:.1f})")
                print(f"ATR14   : {ind['atr']:.0f}")
                if above:
                    print(f"Trend   : {above}")
                vol_ratio = ind.get("vol_ratio")
                print(f"Vol/MA20: {vol_ratio:.2f}x" if vol_ratio else "Vol/MA20: n/a")
        except FileNotFoundError:
            if args.symbol:
                print(f"[ERROR] No data for {sym}. Run init-data first.")
        except Exception as exc:
            if args.symbol:
                print(f"[ERROR] {sym}: {exc}")

    if not args.symbol:
        buys = [(s, r) for s, r in results if r.action == "BUY"]
        sells = [(s, r) for s, r in results if r.action == "SELL"]
        if macro_ctx is not None:
            macro_ok = macro_ctx.get("macro_above_ema50")
            tag = "BULLISH (VN30 > EMA50)" if macro_ok else "BEARISH (VN30 ≤ EMA50) — BUY blocked"
            print(f"Macro regime   : {tag}")
        print(f"Scanned {len(results)} symbols — BUY: {len(buys)}, SELL: {len(sells)}, HOLD: {len(results)-len(buys)-len(sells)}")
        if buys:
            print("\n--- BUY signals ---")
            for s, r in sorted(buys, key=lambda x: -x[1].score):
                print(f"  {s:6s}  score={r.score:+.3f}  regime={r.regime}  RSI={r.indicators['rsi']:.0f}")
        if sells:
            print("\n--- SELL signals ---")
            for s, r in sorted(sells, key=lambda x: x[1].score):
                print(f"  {s:6s}  score={r.score:+.3f}  regime={r.regime}  RSI={r.indicators['rsi']:.0f}")


def cmd_update_daily(args):
    config = load_config()
    from data_sources.yfinance_client import YFinanceClient
    from data_sources.ssi_data_client import SSIDataClient
    from core.data_manager import DataManager

    data_source_cls = {"YFINANCE": YFinanceClient, "SSI": SSIDataClient}[
        config["data_source"]
    ]
    dm = DataManager(data_source_cls())
    status = dm.update_daily()
    ok = sum(1 for v in status.values() if v)
    fail = [s for s, v in status.items() if not v]
    print(f"update-daily: {ok}/{len(status)} success")
    if fail:
        print(f"Failed: {fail}")


def cmd_validate(args):
    config = load_config()
    from data_sources.yfinance_client import YFinanceClient
    from data_sources.ssi_data_client import SSIDataClient
    from core.data_manager import DataManager

    data_source_cls = {"YFINANCE": YFinanceClient, "SSI": SSIDataClient}[
        config["data_source"]
    ]
    dm = DataManager(data_source_cls())
    exchange = args.exchange or "HOSE"
    symbols = [args.symbol] if args.symbol else dm.get_universe(exchange)
    errors = 0
    for sym in symbols:
        report = dm.validate_data(sym, exchange=exchange)
        if report.has_warnings:
            print(f"[WARN] {sym}: {'; '.join(report.warnings)}")
            errors += 1
        else:
            print(f"[OK]   {sym}")
    print(f"\n{len(symbols) - errors}/{len(symbols)} symbols clean.")


def cmd_backtest(args):
    config = load_config()
    from core.backtester import Backtester
    bt = Backtester(config)
    result = bt.run(symbols=[args.symbol], years=args.years)
    print(result.summary())
    if args.trades and result.trades:
        print("\n--- Trades ---")
        print(f"{'Entry':10}  {'Exit':10}  {'Entry$':>10}  {'Exit$':>10}  {'Net P&L':>12}  Result")
        for t in result.trades:
            tag = "WIN " if t.net_pnl > 0 else "LOSS"
            print(f"{t.entry_date}  {t.exit_date}  {t.entry_price:>10,.0f}  "
                  f"{t.exit_price:>10,.0f}  {t.net_pnl:>+12,.0f}  {tag}")


def cmd_backtest_all(args):
    config = load_config()
    from core.backtester import Backtester
    bt = Backtester(config)
    result = bt.run_all(walk_forward=args.walk_forward, split=args.split)
    print(result.summary())


def _setup_logging() -> None:
    """Configure file-based logging: bot.log, trades.log, errors.log, scan.log."""
    from logging.handlers import RotatingFileHandler

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console — INFO+
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
               for h in root.handlers):
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    def _add_file_handler(filename: str, level: int, logger_name: str | None = None) -> None:
        target = logging.getLogger(logger_name) if logger_name else root
        fh = RotatingFileHandler(logs_dir / filename, maxBytes=10 * 1024 * 1024, backupCount=5)
        fh.setLevel(level)
        fh.setFormatter(fmt)
        target.addHandler(fh)

    _add_file_handler("bot.log", logging.INFO)
    _add_file_handler("errors.log", logging.ERROR)
    _add_file_handler("trades.log", logging.DEBUG, "core.portfolio_manager")
    _add_file_handler("scan.log", logging.DEBUG, "core.bot")


def main():
    _setup_logging()

    parser = argparse.ArgumentParser(prog="trading_bot")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("start")

    p_init = sub.add_parser("init-data")
    p_init.add_argument("--years", type=int, default=5)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--symbol", default=None, help="single symbol (omit = scan all universe)")

    sub.add_parser("update-daily")
    sub.add_parser("scan-signals")
    sub.add_parser("place-orders")

    p_val = sub.add_parser("validate")
    p_val.add_argument("--symbol", default=None, help="single symbol (omit = all)")
    p_val.add_argument("--exchange", default="HOSE", choices=["HOSE", "HNX"])

    p_bt = sub.add_parser("backtest")
    p_bt.add_argument("symbol")
    p_bt.add_argument("--years", type=int, default=3)
    p_bt.add_argument("--trades", action="store_true", help="print individual trade list")

    p_bta = sub.add_parser("backtest-all")
    p_bta.add_argument("--walk-forward", action="store_true")
    p_bta.add_argument("--split", type=float, default=0.7)

    args = parser.parse_args()

    if args.command == "scan-signals":
        cmd_scan_signals(args)
    elif args.command == "place-orders":
        cmd_place_orders(args)
    elif args.command == "scan":
        cmd_scan(args)
    elif args.command == "update-daily":
        cmd_update_daily(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "start":
        cmd_start(args)
    elif args.command == "init-data":
        cmd_init_data(args)
    elif args.command == "backtest":
        cmd_backtest(args)
    elif args.command == "backtest-all":
        cmd_backtest_all(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
