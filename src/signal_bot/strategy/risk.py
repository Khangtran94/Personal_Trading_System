from __future__ import annotations

from dataclasses import dataclass

from signal_bot.config import get_settings
from signal_bot.exchange.models import Direction
from signal_bot.strategy.entry import EntryPlan


@dataclass
class RiskSuggestion:
    """Suggested size based on fixed % account risk and SL distance."""

    entry_mid: float
    sl_distance_pct: float  # e.g. 1.2 means 1.2%
    risk_usd: float
    notional_usd: float
    margin_usd: float
    leverage: float
    risk_pct: float  # account % used for this trade


def suggest_risk(plan: EntryPlan, direction: Direction) -> RiskSuggestion | None:
    """
    Size so that if SL is hit, loss ≈ RISK_PER_TRADE_PCT of ACCOUNT_EQUITY.

    notional = risk_usd / (sl_distance / entry)
    margin   = notional / suggested_leverage
    """
    settings = get_settings()
    equity = settings.account_equity
    risk_pct = settings.risk_per_trade_pct
    lev = settings.suggested_leverage

    if equity <= 0 or risk_pct <= 0 or lev <= 0:
        return None

    entry_mid = (plan.entry_low + plan.entry_high) / 2.0
    if entry_mid <= 0:
        return None

    if direction == "LONG":
        # Conservative: risk measured from mid of entry zone down to SL
        sl_dist = entry_mid - plan.stop_loss
    else:
        sl_dist = plan.stop_loss - entry_mid

    if sl_dist <= 0:
        return None

    sl_distance_pct = (sl_dist / entry_mid) * 100.0
    risk_usd = equity * (risk_pct / 100.0)
    # notional such that notional * (sl_dist/entry) = risk_usd
    notional_usd = risk_usd / (sl_dist / entry_mid)
    margin_usd = notional_usd / lev

    return RiskSuggestion(
        entry_mid=round(entry_mid, 6),
        sl_distance_pct=round(sl_distance_pct, 3),
        risk_usd=round(risk_usd, 2),
        notional_usd=round(notional_usd, 2),
        margin_usd=round(margin_usd, 2),
        leverage=lev,
        risk_pct=risk_pct,
    )
