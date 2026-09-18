from __future__ import annotations

"""Market regime filters + ranking applied after per-symbol scoring.

1. ATR% filter – skip low-volatility setups that rarely reach TP.
2. Batch same-direction filter – only trade a direction when enough
   coins agree in the same scan cycle (momentum confirmation).
3. Ranking + selection – rank by ATR% then entry quality; select Top 1–2
   per direction with optional capital split.
"""

from dataclasses import dataclass, field

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
    # Ranking / selection fields (filled later)
    entry_quality: float = 0.0  # lower = closer to ideal EMA zone (better)
    rank: int = 0  # 1 = best in its direction for this batch
    selected: bool = False  # True → will be emitted / simulated
    capital_pct: float = 0.0  # % of the direction's capital allocated to this coin
    # Keep original snapshot close/ema for quality calc if needed later
    close: float | None = None
    ema20: float | None = None


def compute_atr_pct(snapshot: IndicatorSnapshot) -> float | None:
    """ATR as percent of close price. None if data missing."""
    if snapshot.atr is None or snapshot.close is None or snapshot.close <= 0:
        return None
    return (snapshot.atr / snapshot.close) * 100.0


def compute_entry_quality(snapshot: IndicatorSnapshot, direction: Direction) -> float:
    """
    Distance of current price from ideal EMA20 entry zone.
    Lower value = better (price closer to the preferred entry area).

    Ideal zone centre is EMA20. We return |close - ema20| / ATR
    so the metric is volatility-normalised.
    """
    if (
        snapshot.close is None
        or snapshot.ema20 is None
        or snapshot.atr is None
        or snapshot.atr <= 0
    ):
        return 999.0  # worst possible
    return abs(snapshot.close - snapshot.ema20) / snapshot.atr


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


def _rank_and_select_direction(
    candidates: list[SignalCandidate],
    closeness_ratio: float,
    split_mode: str,
) -> list[SignalCandidate]:
    """
    Rank one direction (LONG or SHORT) and mark selected + capital_pct.

    Primary sort  : ATR% descending
    Secondary sort: entry_quality ascending (closer to EMA = better)
    """
    if not candidates:
        return []

    # Sort: higher ATR% first, then better (lower) entry_quality
    ranked = sorted(
        candidates,
        key=lambda c: (-c.atr_pct, c.entry_quality),
    )

    for i, c in enumerate(ranked, start=1):
        c.rank = i
        c.selected = False
        c.capital_pct = 0.0

    # Always take Rank 1
    ranked[0].selected = True
    ranked[0].capital_pct = 100.0

    if len(ranked) >= 2:
        top1_atr = ranked[0].atr_pct
        top2_atr = ranked[1].atr_pct
        # Closeness: Top2 must be within (1 - closeness) of Top1
        # e.g. closeness_ratio=0.75 → Top2 ATR% >= Top1 * 0.75
        if top2_atr >= top1_atr * closeness_ratio:
            ranked[1].selected = True
            if split_mode == "70_30":
                ranked[0].capital_pct = 70.0
                ranked[1].capital_pct = 30.0
            else:  # default 50_50
                ranked[0].capital_pct = 50.0
                ranked[1].capital_pct = 50.0
        else:
            logger.info(
                f"Rank closeness drop: {ranked[1].symbol} ATR%={top2_atr:.3f} "
                f"< {top1_atr:.3f} × {closeness_ratio:.2f}"
            )

    selected = [c for c in ranked if c.selected]
    logger.info(
        f"Rank {candidates[0].direction}: "
        f"{[f'{c.symbol}(R{c.rank},ATR={c.atr_pct:.2f},cap={c.capital_pct:.0f}%)' for c in ranked]} "
        f"→ selected {[c.symbol for c in selected]}"
    )
    return ranked


def rank_and_select(
    candidates: list[SignalCandidate],
    closeness_ratio: float | None = None,
    split_mode: str | None = None,
) -> list[SignalCandidate]:
    """
    Rank candidates per direction and mark which ones are selected
    together with capital allocation.

    Returns the full list (selected + not-selected) so callers can
    still track the ones that were filtered out by ranking.
    """
    settings = get_settings()
    ratio = (
        closeness_ratio
        if closeness_ratio is not None
        else settings.rank_closeness_ratio
    )
    mode = split_mode if split_mode is not None else settings.capital_split_mode

    longs = [c for c in candidates if c.direction == "LONG"]
    shorts = [c for c in candidates if c.direction == "SHORT"]

    ranked_longs = _rank_and_select_direction(longs, ratio, mode)
    ranked_shorts = _rank_and_select_direction(shorts, ratio, mode)

    return ranked_longs + ranked_shorts
