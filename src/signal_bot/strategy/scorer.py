from __future__ import annotations

from signal_bot.config import get_settings
from signal_bot.exchange.models import Direction
from signal_bot.indicators.signals import IndicatorSnapshot, SignalResult


class Scorer:
    """Weighted score from -14 to +14. Decision thresholds from config."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def score(self, snapshot: IndicatorSnapshot) -> tuple[int, list[SignalResult]]:
        total = 0
        ordered: list[SignalResult] = []
        for name in ["EMA", "Supertrend", "MACD_DIF", "Volume", "RSI", "KDJ", "StochRSI", "Williams_R"]:
            r = snapshot.results.get(name)
            if r:
                total += r.weight
                ordered.append(r)
        return total, ordered

    def decide(self, total: int) -> Direction | None:
        if total >= self.settings.score_buy_threshold:
            return "LONG"
        if total <= self.settings.score_sell_threshold:
            return "SHORT"
        return None

    def apply_protection(self, direction: Direction, snapshot: IndicatorSnapshot) -> bool:
        """Return True if signal should be discarded (exhausted move)."""
        rsi = snapshot.rsi
        if rsi is None:
            return False
        if direction == "LONG" and rsi > 80:
            return True
        if direction == "SHORT" and rsi < 20:
            return True
        return False
