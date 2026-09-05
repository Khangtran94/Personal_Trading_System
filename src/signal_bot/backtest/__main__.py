from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from signal_bot.backtest.data import default_symbols
from signal_bot.backtest.engine import run_backtest
from signal_bot.backtest.report import build_report, format_report, trades_to_rows


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-symbol signal strategy backtest")
    p.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Comma-separated symbols (default: top liquid 10)",
    )
    p.add_argument("--days", type=int, default=60, help="Lookback days (default 60)")
    p.add_argument(
        "--step",
        type=int,
        default=1,
        help="Evaluate every N 5m bars (1=every bar, 3≈15m cadence)",
    )
    p.add_argument(
        "--max-hold-bars",
        type=int,
        default=96,
        help="Max 5m bars to hold (96 ≈ 8h)",
    )
    p.add_argument("--no-cache", action="store_true", help="Ignore kline disk cache")
    p.add_argument(
        "--csv",
        type=str,
        default="",
        help="Optional path to write trade log CSV",
    )
    p.add_argument("--log-level", type=str, default="INFO")
    return p.parse_args()


async def async_main() -> None:
    args = parse_args()
    logger.remove()
    logger.add(sys.stderr, level=args.log_level.upper())

    if args.symbols.strip():
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = default_symbols()

    logger.info(f"Symbols ({len(symbols)}): {symbols}")
    trades = await run_backtest(
        symbols,
        days=args.days,
        max_hold_bars=args.max_hold_bars,
        step_bars=max(1, args.step),
        use_cache=not args.no_cache,
    )

    report = build_report(trades)
    print(format_report(report, args.days, symbols))

    out = args.csv.strip() or str(Path("data") / f"backtest_{args.days}d.csv")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    rows = trades_to_rows(trades)
    if rows:
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        logger.info(f"Trade log written → {out}")
    else:
        logger.warning("No trades to write")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
