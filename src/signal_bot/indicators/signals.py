from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from signal_bot.exchange.models import SignalSide


@dataclass
class SignalResult:
    name: str
    side: SignalSide  # BUY / SELL / NEUTRAL
    value: float | None = None  # e.g. RSI number
    weight: int = 0  # signed contribution to final score
    reason: str = ""


@dataclass
class IndicatorSnapshot:
    results: dict[str, SignalResult]
    atr: float | None = None
    ema20: float | None = None
    close: float | None = None
    rsi: float | None = None
