from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from loguru import logger

from signal_bot.backtest.data import fetch_klines_range
from signal_bot.backtest.simulator import SimulatedTrade, simulate_trade
from signal_bot.config import get_settings
from signal_bot.exchange.models import Candle, Direction
from signal_bot.indicators.registry import IndicatorRegistry
from signal_bot.strategy.entry import EntryCalculator
from signal_bot.strategy.scorer import Scorer
from signal_bot.strategy.trend_filter import pass_trend_filter


class TimeCooldown:
    """Cooldown keyed by symbol:direction using signal candle time (backtest-safe)."""

    def __init__(self, minutes: int) -> None:
        self.minutes = minutes
        self._last: dict[str, datetime] = {}

    def is_cooling(self, symbol: str, direction: Direction, at: datetime) -> bool:
        key = f"{symbol}:{direction}"
        last = self._last.get(key)
        if last is None:
            return False
        return (at - last) < timedelta(minutes=self.minutes)

    def mark(self, symbol: str, direction: Direction, at: datetime) -> None:
        self._last[f"{symbol}:{direction}"] = at


def _slice_until(candles: list[Candle], t: datetime) -> list[Candle]:
    """Candles with close_time <= t."""
    out: list[Candle] = []
    for c in candles:
        if c.close_time <= t:
            out.append(c)
        else:
            break
    return out


def _index_after(candles: list[Candle], t: datetime) -> int:
    """First index with open_time > t."""
    for i, c in enumerate(candles):
        if c.open_time > t:
            return i
    return len(candles)


async def backtest_symbol(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    client: httpx.AsyncClient | None = None,
    max_hold_bars: int = 96,
    step_bars: int = 1,
    use_cache: bool = True,
) -> list[SimulatedTrade]:
    """
    Walk 5m closed bars. Trend on 15m, score on 5m — same as live pipeline.
    step_bars=1 evaluates every 5m close (thorough). Use 3 to mimic ~15m cadence.
    """
    settings = get_settings()
    warmup = timedelta(days=5)
    data_start = start - warmup

    k15 = await fetch_klines_range(symbol, "15m", data_start, end, client=client, use_cache=use_cache)
    k5 = await fetch_klines_range(symbol, "5m", data_start, end, client=client, use_cache=use_cache)

    if len(k5) < settings.kline_limit or len(k15) < 60:
        logger.warning(f"{symbol}: not enough history ({len(k5)} 5m, {len(k15)} 15m)")
        return []

    registry = IndicatorRegistry()
    scorer = Scorer()
    entry_calc = EntryCalculator()
    cooldown = TimeCooldown(settings.cooldown_minutes)

    trades: list[SimulatedTrade] = []
    min_bars = 60

    start_i = 0
    for i, c in enumerate(k5):
        if c.open_time >= start and i >= min_bars:
            start_i = i
            break
    else:
        return []

    i = start_i
    while i < len(k5) - 1:
        bar = k5[i]
        t = bar.close_time

        hist5 = k5[max(0, i + 1 - settings.kline_limit) : i + 1]
        hist15 = _slice_until(k15, t)
        hist15 = hist15[-settings.kline_limit :]

        if len(hist5) < min_bars or len(hist15) < min_bars:
            i += step_bars
            continue

        snap15 = registry.compute(hist15)

        for direction in ("LONG", "SHORT"):
            if not pass_trend_filter(snap15, direction):
                continue
            if cooldown.is_cooling(symbol, direction, t):
                continue

            snap5 = registry.compute(hist5)
            total, _ = scorer.score(snap5)
            decided = scorer.decide(total)
            if decided != direction:
                continue
            if scorer.apply_protection(direction, snap5):
                continue

            plan = entry_calc.zone(snap5, direction)
            if plan is None:
                continue

            future = k5[i + 1 :]
            trade = simulate_trade(
                symbol,
                direction,
                total,
                t,
                plan,
                future,
                max_bars=max_hold_bars,
            )
            trades.append(trade)
            cooldown.mark(symbol, direction, t)
            logger.debug(
                f"{symbol} {direction} @ {t.isoformat()} score={total} → {trade.exit_reason} R={trade.r_multiple}"
            )

        i += step_bars

    logger.info(f"{symbol}: {len(trades)} signals in period")
    return trades


async def run_backtest(
    symbols: list[str],
    days: int = 60,
    *,
    max_hold_bars: int = 96,
    step_bars: int = 1,
    use_cache: bool = True,
) -> list[SimulatedTrade]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    all_trades: list[SimulatedTrade] = []

    async with httpx.AsyncClient(
        base_url="https://fapi.binance.com",
        timeout=30.0,
        headers={"User-Agent": "signal-bot-backtest/0.1"},
    ) as client:
        for sym in symbols:
            logger.info(f"Backtesting {sym} ({days}d)…")
            try:
                trades = await backtest_symbol(
                    sym,
                    start,
                    end,
                    client=client,
                    max_hold_bars=max_hold_bars,
                    step_bars=step_bars,
                    use_cache=use_cache,
                )
                all_trades.extend(trades)
            except Exception as e:
                logger.error(f"{sym} failed: {e}")

    all_trades.sort(key=lambda t: t.signal_time)
    return all_trades
