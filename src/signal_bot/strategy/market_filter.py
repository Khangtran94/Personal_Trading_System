from __future__ import annotations

"""Market regime filters applied after per-symbol scoring.

1. ATR% filter – skip low-volatility setups that rarely reach TP.
2. Batch same-direction filter – only trade a direction when enough
   coins agree in the same scan cycle (momentum confirmation).
"""

from dataclasses import dataclass

from loguru import logger

from signal_bot.config import get_settings
from signal_bot.exchange.models import Direction
from signal_bot.indicators.signals import IndicatorSnapshot, SignalResult
from signal_bot.strategy.entry import EntryPlan


@dataclass
class SignalCandidate:
    """Fully validated per-symbol setup, not yet emitted."""

    symbol: str
    direction: Direction
    score: int
    ordered: list[SignalResult]
    plan: EntryPlan
    reason_text: str
    atr_pct: float


def compute_atr_pct(snapshot: IndicatorSnapshot) -> float | None:
    """ATR as percent of close price. None if data missing."""
    if snapshot.atr is None or snapshot.close is None or snapshot.close <= 0:
        return None
    return (snapshot.atr / snapshot.close) * 100.0


def pass_atr_filter(snapshot: IndicatorSnapshot, min_atr_pct: float | None = None) -> bool:
    """
    Require minimum volatility so price has room to reach TP.

    Returns True when ATR% >= threshold (or when filter is disabled / min=0).
    """
    settings = get_settings()
    threshold = settings.min_atr_pct if min_atr_pct is None else min_atr_pct
    if threshold is None or threshold <= 0:
        return True

    atr_pct = compute_atr_pct(snapshot)
    if atr_pct is None:
        return False
    return atr_pct >= threshold


def filter_by_batch_momentum(
    candidates: list[SignalCandidate],
    min_same_direction: int | None = None,
) -> list[SignalCandidate]:
    """
    Keep only directions that have at least `min_same_direction` candidates
    in this scan batch. When the filter is disabled (min <= 1), return all.
    """
    settings = get_settings()
    min_n = (
        settings.min_batch_same_direction
        if min_same_direction is None
        else min_same_direction
    )
    if min_n is None or min_n <= 1:
        return list(candidates)

    long_n = sum(1 for c in candidates if c.direction == "LONG")
    short_n = sum(1 for c in candidates if c.direction == "SHORT")

    keep_long = long_n >= min_n
    keep_short = short_n >= min_n

    if not keep_long and not keep_short:
        logger.info(
            f"Batch momentum filter: skip all "
            f"(LONG={long_n}, SHORT={short_n}, need ≥{min_n})"
        )
        return []

    filtered: list[SignalCandidate] = []
    for c in candidates:
        if c.direction == "LONG" and keep_long:
            filtered.append(c)
        elif c.direction == "SHORT" and keep_short:
            filtered.append(c)
        else:
            logger.info(
                f"Batch momentum filter: drop {c.symbol} {c.direction} "
                f"(direction count below {min_n})"
            )

    logger.info(
        f"Batch momentum filter: LONG {long_n}→{sum(1 for c in filtered if c.direction=='LONG')}, "
        f"SHORT {short_n}→{sum(1 for c in filtered if c.direction=='SHORT')} "
        f"(min={min_n})"
    )
    return filtered
