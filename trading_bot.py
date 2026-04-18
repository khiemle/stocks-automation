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
    from signals.momentum_v1 import MomentumV1

    data_source_cls = {"YFINANCE": YFinanceClient, "SSI": SSIDataClient}[
        config["data_source"]
    ]
    dm = DataManager(data_source_cls())
    engine = MomentumV1()

    symbols = [args.symbol] if args.symbol else list(dict.fromkeys(
        dm.get_universe("HOSE") + dm.get_universe("HNX")
    ))

    results = []
    for sym in symbols:
        try:
            df = dm.get_ohlcv(sym, days=120)
            result = engine.evaluate(df, foreign_flow=None)
            results.append((sym, result))
            if args.symbol:
                ind = result.indicators
                print(f"Symbol  : {sym}")
                print(f"Action  : {result.action}  (score={result.score:+.3f}, confidence={result.confidence:.2f})")
                print(f"Regime  : {result.regime}")
                ema200 = ind.get("ema200")
                ema200_str = f"{ema200:.0f}" if ema200 else "n/a (< 200 bars)"
                print(f"EMA20/60/200: {ind['ema20']:.0f} / {ind['ema60']:.0f} / {ema200_str}")
                above = "✓ above EMA200" if ema200 and float(ind.get("ema20", 0)) > ema200 else ("✗ below EMA200 — BUY blocked" if ema200 else "")
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


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(prog="trading_bot")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("start")

    p_init = sub.add_parser("init-data")
    p_init.add_argument("--years", type=int, default=5)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--symbol", default=None, help="single symbol (omit = scan all universe)")

    sub.add_parser("update-daily")

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

    if args.command == "scan":
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
