from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from signal_bot.exchange.models import Candle, Direction
from signal_bot.strategy.entry import EntryPlan

ExitReason = Literal["TP", "SL", "TIMEOUT", "END"]


@dataclass
class SimulatedTrade:
    symbol: str
    direction: Direction
    signal_time: datetime
    score: int
    entry: float
    stop_loss: float
    take_profit: float
    exit_time: datetime | None
    exit_price: float | None
    exit_reason: ExitReason
    r_multiple: float
    bars_held: int


def simulate_trade(
    symbol: str,
    direction: Direction,
    score: int,
    signal_time: datetime,
    plan: EntryPlan,
    future_candles: list[Candle],
    *,
    max_bars: int = 96,
) -> SimulatedTrade:
    """
    Fill at entry mid. Walk future closed candles.
    Same bar hits both SL and TP → conservative: count as SL.
    """
    entry = (plan.entry_low + plan.entry_high) / 2.0
    sl = plan.stop_loss
    tp = plan.take_profit
    risk = abs(entry - sl)
    if risk <= 0:
        return SimulatedTrade(
            symbol=symbol,
            direction=direction,
            signal_time=signal_time,
            score=score,
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            exit_time=signal_time,
            exit_price=entry,
            exit_reason="END",
            r_multiple=0.0,
            bars_held=0,
        )

    window = future_candles[:max_bars]
    for i, c in enumerate(window):
        if direction == "LONG":
            hit_sl = c.low <= sl
            hit_tp = c.high >= tp
            if hit_sl and hit_tp:
                return _done(symbol, direction, score, signal_time, entry, sl, tp, c, "SL", -1.0, i + 1)
            if hit_sl:
                return _done(symbol, direction, score, signal_time, entry, sl, tp, c, "SL", -1.0, i + 1)
            if hit_tp:
                return _done(
                    symbol, direction, score, signal_time, entry, sl, tp, c, "TP", abs(tp - entry) / risk, i + 1
                )
        else:
            hit_sl = c.high >= sl
            hit_tp = c.low <= tp
            if hit_sl and hit_tp:
                return _done(symbol, direction, score, signal_time, entry, sl, tp, c, "SL", -1.0, i + 1)
            if hit_sl:
                return _done(symbol, direction, score, signal_time, entry, sl, tp, c, "SL", -1.0, i + 1)
            if hit_tp:
                return _done(
                    symbol, direction, score, signal_time, entry, sl, tp, c, "TP", abs(entry - tp) / risk, i + 1
                )

    if window:
        last = window[-1]
        exit_price = last.close
        if direction == "LONG":
            r_mult = (exit_price - entry) / risk
        else:
            r_mult = (entry - exit_price) / risk
        reason: ExitReason = "TIMEOUT" if len(window) >= max_bars else "END"
        return SimulatedTrade(
            symbol=symbol,
            direction=direction,
            signal_time=signal_time,
            score=score,
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            exit_time=last.close_time,
            exit_price=exit_price,
            exit_reason=reason,
            r_multiple=round(r_mult, 4),
            bars_held=len(window),
        )

    return SimulatedTrade(
        symbol=symbol,
        direction=direction,
        signal_time=signal_time,
        score=score,
        entry=entry,
        stop_loss=sl,
        take_profit=tp,
        exit_time=None,
        exit_price=None,
        exit_reason="END",
        r_multiple=0.0,
        bars_held=0,
    )


def _done(
    symbol: str,
    direction: Direction,
    score: int,
    signal_time: datetime,
    entry: float,
    sl: float,
    tp: float,
    candle: Candle,
    reason: ExitReason,
    r_multiple: float,
    bars: int,
) -> SimulatedTrade:
    exit_price = sl if reason == "SL" else tp
    return SimulatedTrade(
        symbol=symbol,
        direction=direction,
        signal_time=signal_time,
        score=score,
        entry=entry,
        stop_loss=sl,
        take_profit=tp,
        exit_time=candle.close_time,
        exit_price=exit_price,
        exit_reason=reason,
        r_multiple=round(r_multiple, 4),
        bars_held=bars,
    )
