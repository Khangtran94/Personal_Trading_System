from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from signal_bot.paper.tracker import PaperTracker


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Forward paper tracker for live signals")
    p.add_argument("--once", action="store_true", help="Check open signals once and exit")
    p.add_argument("--summary", action="store_true", help="Print paper stats only")
    p.add_argument("--max-hold-hours", type=float, default=8.0, help="Timeout after this many hours (default 8)")
    p.add_argument("--log-level", type=str, default="INFO")
    return p.parse_args()


async def async_main() -> None:
    args = parse_args()
    logger.remove()
    logger.add(sys.stderr, level=args.log_level.upper())

    tracker = PaperTracker(max_hold_hours=args.max_hold_hours)

    if args.summary and not args.once:
        print(tracker.format_summary())
        return

    if args.once or not args.summary:
        await tracker.run_once()
        print(tracker.format_summary())
        return

    print(tracker.format_summary())


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
