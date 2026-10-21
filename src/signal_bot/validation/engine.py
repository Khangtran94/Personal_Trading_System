"""Deterministic closed-bar paper engine; standard library only.

Entry: midpoint limit, active from the first full post-signal 5m candle.
Entry+SL in one candle: pessimistic SL. Entry+TP without SL: REVIEW,
because OHLC does not establish whether TP happened before the fill.
Subsequent gaps through a stop exit at the worse candle open.
No fill is inferred across missing candles. R is not account equity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
import math

BAR_MS = 300_000
TERMINAL = {"WIN", "LOSS", "TIMEOUT", "UNFILLED", "INVALID", "REVIEW"}
EXECUTION_MODEL = "limit-midpoint-full-bar-v2"


def quantize(price: float, tick: str, rounding=ROUND_HALF_UP) -> float:
    p, step = Decimal(str(price)), Decimal(tick)
    if not p.is_finite() or not step.is_finite() or step <= 0:
        raise ValueError("Price and tick size must be finite; tick size must be positive")
    return float((p / step).to_integral_value(rounding=rounding) * step)


def precise_plan(ema: float, atr: float, direction: str, sl_multiplier: float,
                 rr: float, tick: str) -> dict:
    if direction not in {"LONG", "SHORT"} or not all(
        math.isfinite(v) and v > 0 for v in (ema, atr, sl_multiplier, rr)
    ):
        raise ValueError("Invalid raw entry-plan inputs")
    low, high = ema - atr * .3, ema + atr * .3
    if direction == "LONG":
        sl = low - atr * sl_multiplier
        tp = high + (high - sl) * rr
        sl_round, tp_round = ROUND_FLOOR, ROUND_CEILING
    else:
        sl = high + atr * sl_multiplier
        tp = low - (sl - low) * rr
        sl_round, tp_round = ROUND_CEILING, ROUND_FLOOR
    return dict(entry_low=quantize(low, tick, ROUND_FLOOR),
                entry_high=quantize(high, tick, ROUND_CEILING),
                stop_loss=quantize(sl, tick, sl_round),
                take_profit=quantize(tp, tick, tp_round), atr=atr)


@dataclass
class Bar:
    open_ms: int
    open: float
    high: float
    low: float
    close: float
    @property
    def end_ms(self):
        return self.open_ms + BAR_MS


@dataclass
class Position:
    symbol: str
    direction: str
    signal_ms: int
    entry: float
    stop: float
    target: float
    tick: str
    entry_window_ms: int = 3_600_000
    hold_ms: int = 28_800_000
    cost_r: float = .05
    state: str = "PENDING_ENTRY"
    next_ms: int | None = None
    fill_ms: int | None = None
    fill_price: float | None = None
    exit_ms: int | None = None
    exit_price: float | None = None
    r_multiple: float | None = None
    net_r: float | None = None
    note: str = ""
    data_issue: str = ""

    @property
    def first_ms(self):
        return ((self.signal_ms + BAR_MS - 1) // BAR_MS) * BAR_MS

    @property
    def entry_deadline(self):
        return self.first_ms + self.entry_window_ms

    @property
    def end_deadline(self):
        return (self.fill_ms + self.hold_ms if self.fill_ms is not None
                else self.entry_deadline + self.hold_ms)


def _finish(p: Position, state: str, price: float, end: int):
    risk = abs(p.fill_price - p.stop)
    r = (price - p.fill_price) / risk * (1 if p.direction == "LONG" else -1)
    p.state, p.exit_price, p.exit_ms = state, price, end
    p.r_multiple, p.net_r = r, r - p.cost_r


def advance(position: Position, bars: list[Bar], now_ms: int) -> Position:
    p = replace(position)
    if p.state in TERMINAL:
        return p
    values = (p.entry, p.stop, p.target, p.cost_r)
    valid = all(math.isfinite(v) for v in values) and min(values[:3]) > 0
    valid = valid and p.direction in {"LONG", "SHORT"} and p.cost_r >= 0
    valid = valid and p.entry_window_ms > 0 and p.hold_ms > 0
    valid = valid and p.entry_window_ms % BAR_MS == 0 and p.hold_ms % BAR_MS == 0
    valid = valid and ((p.stop < p.entry < p.target) if p.direction == "LONG"
                       else (p.target < p.entry < p.stop))
    try:
        valid = valid and all(math.isclose(quantize(v, p.tick), v, rel_tol=0, abs_tol=1e-12)
                              for v in values[:3])
    except (ValueError, ArithmeticError):
        valid = False
    if not valid:
        p.state, p.note = "INVALID", "Non-positive risk, invalid levels, tick size or settings"
        return p
    expected = p.first_ms if p.next_ms is None else p.next_ms
    p.data_issue = ""
    for b in sorted(bars, key=lambda c: c.open_ms):
        if b.open_ms < expected or b.end_ms > now_ms:
            continue
        if b.open_ms != expected:
            p.data_issue = f"Missing closed candle at {expected}; no outcome inferred"
            return p
        if not (all(math.isfinite(v) and v > 0 for v in (b.open,b.high,b.low,b.close))
                and b.low <= min(b.open,b.close) <= max(b.open,b.close) <= b.high):
            p.data_issue = f"Invalid OHLC at {b.open_ms}"
            return p
        fresh = p.state == "PENDING_ENTRY"
        if fresh and b.open_ms >= p.entry_deadline:
            p.state, p.note = "UNFILLED", "Entry limit expired"
            return p
        if fresh:
            marketable = b.open <= p.entry if p.direction == "LONG" else b.open >= p.entry
            if marketable or b.low <= p.entry <= b.high:
                fill = b.open if marketable else p.entry
                crossed_stop = fill <= p.stop if p.direction == "LONG" else fill >= p.stop
                if crossed_stop:
                    p.state, p.note = "REVIEW", "Gap crossed both entry and stop before an observable fill"
                    return p
                p.state, p.fill_ms, p.fill_price = "OPEN", b.open_ms, fill
        if p.state == "OPEN":
            is_long = p.direction == "LONG"
            hit_sl = b.low <= p.stop if is_long else b.high >= p.stop
            hit_tp = b.high >= p.target if is_long else b.low <= p.target
            if hit_sl:
                exit_price = min(p.stop,b.open) if is_long else max(p.stop,b.open)
                _finish(p, "LOSS", exit_price, b.end_ms)
            elif hit_tp and fresh and not marketable:
                p.state, p.note = "REVIEW", "Intrabar entry and target touched; ordering unknown"
            elif hit_tp:
                _finish(p, "WIN", p.target, b.end_ms)
            elif b.end_ms >= p.fill_ms + p.hold_ms:
                _finish(p, "TIMEOUT", b.close, b.end_ms)
        elif b.end_ms >= p.entry_deadline:
            p.state, p.note = "UNFILLED", "Entry limit expired"
        expected = b.end_ms
        p.next_ms = expected
        if p.state in TERMINAL:
            return p
    if expected + BAR_MS <= now_ms:
        p.data_issue = f"Missing closed candle at {expected}; waiting for historical backfill"
    return p
