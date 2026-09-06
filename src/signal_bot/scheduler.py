from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from signal_bot.config import get_settings
from signal_bot.main import SignalPipeline
from signal_bot.paper.tracker import PaperTracker


class BotScheduler:
    def __init__(self, pipeline: SignalPipeline) -> None:
        self.pipeline = pipeline
        self.settings = get_settings()
        self.scheduler = AsyncIOScheduler(timezone=self.settings.timezone)
        self.paper = PaperTracker(max_hold_hours=8.0)
        self._running = False

    def _is_active_hours(self) -> bool:
        now = datetime.now(ZoneInfo(self.settings.timezone))
        start_h, start_m = map(int, self.settings.active_start.split(":"))
        end_h, end_m = map(int, self.settings.active_end.split(":"))
        start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        return start <= now <= end

    async def _scan_job(self) -> None:
        if not self._is_active_hours():
            logger.debug("Outside active hours – skip scan")
            return
        try:
            await self.pipeline.run_once()
        except Exception as e:
            logger.exception(f"Pipeline error: {e}")

    async def _paper_job(self) -> None:
        try:
            await self.paper.run_once()
        except Exception as e:
            logger.exception(f"Paper tracker error: {e}")

    def start(self) -> None:
        self.scheduler.add_job(
            self._scan_job,
            trigger="interval",
            minutes=3,
            id="scan_and_signal",
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self._paper_job,
            trigger="interval",
            minutes=5,
            id="paper_tracker",
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        self._running = True
        logger.info(
            "Scheduler started (scan every 3 min in active hours; "
            "paper tracker every 5 min)"
        )

    def stop(self) -> None:
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Scheduler stopped")
