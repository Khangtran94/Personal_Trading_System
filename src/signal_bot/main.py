from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger

# Ensure src/ is on path when running as script (so "import signal_bot" works)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from signal_bot.config import get_settings
from signal_bot.database.repository import SignalRepository
from signal_bot.exchange.client import BinanceFuturesClient
from signal_bot.indicators.registry import IndicatorRegistry
from signal_bot.scanner.volume_scanner import VolumeScanner
from signal_bot.strategy.cooldown import CooldownManager
from signal_bot.strategy.entry import EntryCalculator
from signal_bot.strategy.scorer import Scorer
from signal_bot.strategy.trend_filter import pass_trend_filter
from signal_bot.notify.bot import TelegramNotifier
from signal_bot.notify.formatter import format_signal


class SignalPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.registry = IndicatorRegistry()
        self.scorer = Scorer()
        self.entry_calc = EntryCalculator()
        self.cooldown = CooldownManager()
        self.repo = SignalRepository()
        self.notifier = TelegramNotifier()

    async def analyze_symbol(self, client: BinanceFuturesClient, symbol: str) -> None:
        # 15m for trend filter
        klines_15m = await client.get_klines(symbol, self.settings.main_tf, self.settings.kline_limit)
        if len(klines_15m) < 60:
            return

        snap_15m = self.registry.compute(klines_15m)

        # Check both directions against trend gate
        for direction in ("LONG", "SHORT"):
            if not pass_trend_filter(snap_15m, direction):
                continue
            if self.cooldown.is_cooling(symbol, direction):
                logger.debug(f"{symbol} {direction} still in cooldown")
                continue

            # Confirmation on 5m + entry timing context on 3m (we use 5m for scoring for stability)
            klines_5m = await client.get_klines(symbol, self.settings.confirm_tf, self.settings.kline_limit)
            if len(klines_5m) < 60:
                continue
            snap = self.registry.compute(klines_5m)

            total, ordered = self.scorer.score(snap)
            decided = self.scorer.decide(total)
            if decided != direction:
                continue

            if self.scorer.apply_protection(direction, snap):
                logger.info(f"Discard {symbol} {direction} – RSI protection")
                continue

            plan = self.entry_calc.zone(snap, direction)
            if plan is None:
                continue

            # Format + send + store
            reason_text = "\n".join(r.reason for r in ordered)
            msg = format_signal(symbol, direction, total, ordered, plan)
            await self.notifier.send(msg)
            self.repo.save(symbol, direction, total, reason_text, plan)
            self.cooldown.mark(symbol, direction)
            logger.success(f"SIGNAL emitted: {symbol} {direction} score={total}")

    async def run_once(self) -> None:
        logger.info("Starting scan cycle…")
        async with BinanceFuturesClient() as client:
            scanner = VolumeScanner(client)
            symbols = await scanner.scan()
            for symbol in symbols:
                try:
                    await self.analyze_symbol(client, symbol)
                except Exception as e:
                    logger.warning(f"Error analyzing {symbol}: {e}")
        logger.info("Scan cycle finished")


async def main() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)

    pipeline = SignalPipeline()
    logger.info("Signal Bot ready (SIGNAL-ONLY, never places trades)")

    # Manual one-shot or continuous
    if "--once" in sys.argv:
        await pipeline.run_once()
    else:
        from signal_bot.scheduler import BotScheduler

        scheduler = BotScheduler(pipeline)
        scheduler.start()
        # Keep alive
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
