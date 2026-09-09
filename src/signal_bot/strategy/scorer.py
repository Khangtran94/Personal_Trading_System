from __future__ import annotations

from signal_bot.config import get_settings
from signal_bot.exchange.models import Direction
from signal_bot.indicators.signals import IndicatorSnapshot, SignalResult
from signal_bot.strategy.profiles import DEFAULT_PROFILE, get_weights


class Scorer:
    """Weighted score; weights come from a named profile (default | no_volume).

    Decision supports an optional closed range:
      LONG  when buy_threshold  <= score <= buy_max   (buy_max=None → no upper cap)
      SHORT when sell_threshold <= score <= sell_max  (sell_max=None → no lower cap toward zero)
    """

    def __init__(
        self,
        profile: str | None = None,
        buy_threshold: int | None = None,
        sell_threshold: int | None = None,
        buy_max: int | None = None,
        sell_max: int | None = None,
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
        # Upper/lower caps. None = unlimited (legacy behaviour).
        self.buy_max = (
            buy_max if buy_max is not None else self.settings.score_buy_max
        )
        self.sell_max = (
            sell_max if sell_max is not None else self.settings.score_sell_max
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
            # Re-bind weight for this profile (registry may have baked default weights)
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
        # LONG: score in [buy_threshold, buy_max]
        #   buy_max=None → no upper cap (legacy: score >= buy_threshold)
        if total >= self.buy_threshold:
            if self.buy_max is None or total <= self.buy_max:
                return "LONG"

        # SHORT range:
        #   sell_threshold = more extreme (e.g. -12)
        #   sell_max       = closer to zero (e.g. -10)
        #   sell_max=None  → legacy: score <= sell_threshold
        if self.sell_max is None:
            if total <= self.sell_threshold:
                return "SHORT"
        else:
            # Closed range [sell_threshold, sell_max]  e.g. [-12, -10]
            lo = min(self.sell_threshold, self.sell_max)
            hi = max(self.sell_threshold, self.sell_max)
            if lo <= total <= hi:
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
