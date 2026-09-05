from __future__ import annotations

from dataclasses import dataclass

from signal_bot.config import get_settings
from signal_bot.exchange.models import Direction
from signal_bot.indicators.signals import IndicatorSnapshot


@dataclass
class EntryPlan:
    entry_low: float
    entry_high: float
    stop_loss: float
    take_profit: float
    atr: float


class EntryCalculator:
    """
    Entry zone around EMA20 ± ATR buffer.
    SL = ATR × 1.5, TP = risk × RR_RATIO (default 1:2).
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def zone(self, snapshot: IndicatorSnapshot, direction: Direction) -> EntryPlan | None:
        if snapshot.ema20 is None or snapshot.atr is None or snapshot.close is None:
            return None

        atr = snapshot.atr
        ema20 = snapshot.ema20
        buffer = atr * 0.3  # small buffer around EMA20

        if direction == "LONG":
            entry_low = ema20 - buffer
            entry_high = ema20 + buffer
            # Prefer not chasing: if price already far above, skip later
            stop_loss = entry_low - atr * self.settings.atr_sl_multiplier
            risk = entry_high - stop_loss  # conservative
            take_profit = entry_high + risk * self.settings.rr_ratio
        else:  # SHORT
            entry_low = ema20 - buffer
            entry_high = ema20 + buffer
            stop_loss = entry_high + atr * self.settings.atr_sl_multiplier
            risk = stop_loss - entry_low
            take_profit = entry_low - risk * self.settings.rr_ratio

        # Round to reasonable precision (will be refined by symbol filters later)
        def r(v: float) -> float:
            return round(v, 4)

        return EntryPlan(
            entry_low=r(entry_low),
            entry_high=r(entry_high),
            stop_loss=r(stop_loss),
            take_profit=r(take_profit),
            atr=r(atr),
        )
