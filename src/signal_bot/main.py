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
from signal_bot.notify.bot import TelegramNotifier
from signal_bot.notify.formatter import format_signal
from signal_bot.scanner.volume_scanner import VolumeScanner
from signal_bot.strategy.cooldown import CooldownManager
from signal_bot.strategy.entry import EntryCalculator
from signal_bot.strategy.market_filter import (
    SignalCandidate,
    compute_atr_pct,
    compute_entry_quality,
    filter_by_batch_momentum,
    pass_atr_filter,
    rank_and_select,
)
from signal_bot.strategy.scorer import Scorer
from signal_bot.strategy.trend_filter import pass_trend_filter


class SignalPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.registry = IndicatorRegistry()
        self.scorer = Scorer()
        self.entry_calc = EntryCalculator()
        self.cooldown = CooldownManager()
        self.repo = SignalRepository()
        self.notifier = TelegramNotifier()
        # Cycle stats
        self._trend_pass = 0
        self._near_threshold: list[tuple[str, str, int]] = []
        self._atr_rejected = 0
        self._emitted = 0

    async def collect_candidates(
        self, client: BinanceFuturesClient, symbol: str
    ) -> list[SignalCandidate]:
        """Analyze one symbol; return zero or more validated candidates (no emit)."""
        candidates: list[SignalCandidate] = []

        # 15m for trend filter
        klines_15m = await client.get_klines(
            symbol, self.settings.main_tf, self.settings.kline_limit
        )
        if len(klines_15m) < 60:
            return candidates

        snap_15m = self.registry.compute(klines_15m)

        # Confirmation on 5m (stable scoring + ATR%)
        klines_5m = await client.get_klines(
            symbol, self.settings.confirm_tf, self.settings.kline_limit
        )
        if len(klines_5m) < 60:
            return candidates
        snap = self.registry.compute(klines_5m)

        for direction in ("LONG", "SHORT"):
            if not pass_trend_filter(snap_15m, direction):
                continue
            self._trend_pass += 1
            if self.cooldown.is_cooling(symbol, direction):
                logger.debug(f"{symbol} {direction} still in cooldown")
                continue

            total, ordered = self.scorer.score(snap)
            decided = self.scorer.decide(total)
            if decided != direction:
                # Track near-misses for visibility
                if direction == "LONG":
                    lo, hi = self.settings.score_buy_threshold, self.settings.score_buy_max
                    need = f"{lo}..{hi}" if hi is not None else f">={lo}"
                else:
                    lo, hi = self.settings.score_sell_threshold, self.settings.score_sell_max
                    need = f"{lo}..{hi}" if hi is not None else f"<={lo}"
                if abs(total) >= abs(self.settings.score_buy_threshold) - 3:
                    self._near_threshold.append((symbol, direction, total))
                    logger.info(
                        f"Near miss {symbol} {direction}: score={total} (need {need})"
                    )
                else:
                    logger.debug(
                        f"{symbol} {direction}: trend OK, score={total} outside range {need}"
                    )
                continue

            if self.scorer.apply_protection(direction, snap):
                logger.info(f"Discard {symbol} {direction} – RSI protection")
                continue

            # ATR% volatility filter
            if not pass_atr_filter(snap):
                atr_pct = compute_atr_pct(snap)
                self._atr_rejected += 1
                atr_txt = f"{atr_pct:.3f}" if atr_pct is not None else "n/a"
                logger.info(
                    f"ATR filter reject {symbol} {direction}: "
                    f"ATR%={atr_txt} (min={self.settings.min_atr_pct})"
                )
                continue

            plan = self.entry_calc.zone(snap, direction)
            if plan is None:
                logger.debug(f"{symbol} {direction}: no entry plan (missing ATR/EMA)")
                continue

            atr_pct = compute_atr_pct(snap) or 0.0
            entry_quality = compute_entry_quality(snap, direction)
            reason_text = "\n".join(r.reason for r in ordered)
            candidates.append(
                SignalCandidate(
                    symbol=symbol,
                    direction=direction,
                    score=total,
                    ordered=ordered,
                    plan=plan,
                    reason_text=reason_text,
                    atr_pct=atr_pct,
                    entry_quality=entry_quality,
                    close=snap.close,
                    ema20=snap.ema20,
                )
            )

        return candidates

    async def _emit(self, candidate: SignalCandidate) -> None:
        msg = format_signal(
            candidate.symbol,
            candidate.direction,
            candidate.score,
            candidate.ordered,
            candidate.plan,
            rank=candidate.rank,
            capital_pct=candidate.capital_pct,
            atr_pct=candidate.atr_pct,
        )
        await self.notifier.send(msg)
        self.repo.save(
            candidate.symbol,
            candidate.direction,
            candidate.score,
            candidate.reason_text,
            candidate.plan,
        )
        self.cooldown.mark(candidate.symbol, candidate.direction)
        self._emitted += 1
        logger.success(
            f"SIGNAL emitted: {candidate.symbol} {candidate.direction} "
            f"rank={candidate.rank} capital={candidate.capital_pct:.0f}% "
            f"score={candidate.score} ATR%={candidate.atr_pct:.3f}"
        )

    async def run_once(self) -> None:
        self._trend_pass = 0
        self._near_threshold = []
        self._atr_rejected = 0
        self._emitted = 0
        logger.info(
            f"Starting scan cycle… "
            f"(min_atr_pct={self.settings.min_atr_pct}, "
            f"min_batch_same_dir={self.settings.min_batch_same_direction}, "
            f"ranking={self.settings.enable_ranking}, "
            f"split={self.settings.capital_split_mode}, "
            f"closeness={self.settings.rank_closeness_ratio})"
        )

        all_candidates: list[SignalCandidate] = []
        async with BinanceFuturesClient() as client:
            scanner = VolumeScanner(client)
            symbols = await scanner.scan()
            for symbol in symbols:
                try:
                    found = await self.collect_candidates(client, symbol)
                    all_candidates.extend(found)
                except Exception as e:
                    logger.warning(f"Error analyzing {symbol}: {e}")

        # Batch same-direction momentum filter
        before = len(all_candidates)
        filtered = filter_by_batch_momentum(all_candidates)
        dropped_batch = before - len(filtered)

        # Ranking + selection (Top 1–2 per direction)
        if self.settings.enable_ranking and filtered:
            ranked = rank_and_select(filtered)
            selected = [c for c in ranked if c.selected]
            not_selected = [c for c in ranked if not c.selected]
            if not_selected:
                logger.info(
                    f"Ranking kept {len(selected)} / dropped {len(not_selected)}: "
                    f"{[f'{c.symbol}({c.direction} R{c.rank})' for c in not_selected]}"
                )
        else:
            # Ranking disabled → treat every filtered candidate as selected with 100%
            ranked = filtered
            for c in ranked:
                c.selected = True
                c.rank = 1
                c.capital_pct = 100.0
            selected = ranked

        for candidate in selected:
            try:
                await self._emit(candidate)
            except Exception as e:
                logger.warning(
                    f"Error emitting {candidate.symbol} {candidate.direction}: {e}"
                )

        logger.info(
            f"Scan cycle finished | trend_pass={self._trend_pass} | "
            f"near_miss={len(self._near_threshold)} | "
            f"atr_reject={self._atr_rejected} | "
            f"batch_drop={dropped_batch} | "
            f"candidates={before}→{len(filtered)}→selected={len(selected)} | "
            f"signals={self._emitted}"
        )
        if self._emitted == 0 and self._near_threshold:
            top = sorted(self._near_threshold, key=lambda x: abs(x[2]), reverse=True)[:5]
            for sym, d, sc in top:
                logger.info(f"  closest: {sym} {d} score={sc}")


async def test_telegram() -> None:
    """Send a one-line test message to verify token + chat_id."""
    notifier = TelegramNotifier()
    ok = await notifier.send("Signal Bot test ✅ – connection OK")
    if ok:
        logger.success("Telegram test message sent")
    else:
        logger.error(
            "Telegram test failed – check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
        )


async def main() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)

    if "--test-telegram" in sys.argv:
        await test_telegram()
        return

    pipeline = SignalPipeline()
    logger.info("Signal Bot ready (SIGNAL-ONLY, never places trades)")

    if "--once" in sys.argv:
        await pipeline.run_once()
    else:
        from signal_bot.scheduler import BotScheduler

        scheduler = BotScheduler(pipeline)
        scheduler.start()
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
