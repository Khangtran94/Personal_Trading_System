from __future__ import annotations

from signal_bot.exchange.models import Direction
from signal_bot.indicators.signals import IndicatorSnapshot


def pass_trend_filter(snapshot: IndicatorSnapshot, direction: Direction) -> bool:
    """
    15m trend gate:
    LONG  only when EMA BUY + Supertrend BUY
    SHORT only when EMA SELL + Supertrend SELL
    """
    ema = snapshot.results.get("EMA")
    st = snapshot.results.get("Supertrend")
    if not ema or not st:
        return False

    if direction == "LONG":
        return ema.side == "BUY" and st.side == "BUY"
    if direction == "SHORT":
        return ema.side == "SELL" and st.side == "SELL"
    return False
