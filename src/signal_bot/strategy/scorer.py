from __future__ import annotations

from signal_bot.config import get_settings
from signal_bot.exchange.models import Direction
from signal_bot.indicators.signals import IndicatorSnapshot, SignalResult
from signal_bot.strategy.profiles import DEFAULT_PROFILE, get_weights


class Scorer:
    """Weighted score; weights come from a named profile (default | no_volume)."""

    def __init__(
        self,
        profile: str | None = None,
        buy_threshold: int | None = None,
        sell_threshold: int | None = None,
    ) -> None:
        self.settings = get_settings()
        self.profile = profile or DEFAULT_PROFILE
        self.weights = get_weights(self.profile)
        self.buy_threshold = (
            buy_threshold
            if buy_threshold is not None
            else self.settings.score_buy_threshold
        )
        self.sell_threshold = (
            sell_threshold
            if sell_threshold is not None
            else self.settings.score_sell_threshold
        )

    def score(self, snapshot: IndicatorSnapshot) -> tuple[int, list[SignalResult]]:
        total = 0
        ordered: list[SignalResult] = []
        for name in [
            "EMA",
            "Supertrend",
            "MACD_DIF",
            "Volume",
            "RSI",
            "KDJ",
            "StochRSI",
            "Williams_R",
        ]:
            r = snapshot.results.get(name)
            if not r:
                continue
            w = self.weights.get(name, 0)
            if r.side == "BUY":
                signed = w
            elif r.side == "SELL":
                signed = -w
            else:
                signed = 0
            adjusted = SignalResult(
                name=r.name,
                side=r.side,
                value=r.value,
                weight=signed,
                reason=r.reason,
            )
            total += signed
            ordered.append(adjusted)
        return total, ordered

    def decide(self, total: int) -> Direction | None:
        if total >= self.buy_threshold:
            return "LONG"
        if total <= self.sell_threshold:
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
