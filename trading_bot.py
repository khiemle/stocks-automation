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


def cmd_backtest(args):
    config = load_config()
    from core.backtester import Backtester
    bt = Backtester(config)
    result = bt.run(symbols=[args.symbol], years=args.years)
    print(result.summary())


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

    p_bt = sub.add_parser("backtest")
    p_bt.add_argument("symbol")
    p_bt.add_argument("--years", type=int, default=3)

    p_bta = sub.add_parser("backtest-all")
    p_bta.add_argument("--walk-forward", action="store_true")
    p_bta.add_argument("--split", type=float, default=0.7)

    args = parser.parse_args()

    if args.command == "start":
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
