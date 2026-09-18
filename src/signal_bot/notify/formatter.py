from __future__ import annotations

from signal_bot.exchange.models import Direction
from signal_bot.indicators.signals import SignalResult
from signal_bot.strategy.entry import EntryPlan
from signal_bot.strategy.risk import RiskSuggestion, suggest_risk


def _arrow(side: str) -> str:
    if side == "BUY":
        return "⬆️"
    if side == "SELL":
        return "⬇️"
    return "➖"


def _format_risk_block(risk: RiskSuggestion | None) -> str:
    if risk is None:
        return ""
    return f"""
Risk:
{risk.risk_pct}% account ≈ ${risk.risk_usd}
SL distance:
{risk.sl_distance_pct}%
Notional:
${risk.notional_usd}
Margin @{risk.leverage:.0f}x:
${risk.margin_usd}"""


def format_signal(
    symbol: str,
    direction: Direction,
    score: int,
    results: list[SignalResult],
    plan: EntryPlan,
    rank: int = 0,
    capital_pct: float = 100.0,
    atr_pct: float | None = None,
) -> str:
    """Strict Telegram template. Indicator names English, Action Vietnamese."""
    reason_lines = []
    for r in results:
        arrow = _arrow(r.side)
        reason_lines.append(f"{arrow} {r.reason}")

    reason_block = "\n".join(reason_lines)

    if direction == "LONG":
        dir_line = "LONG ⬆️"
        action = "➡️ MUA LONG"
    else:
        dir_line = "SHORT ⬇️"
        action = "➡️ BÁN SHORT"

    risk = suggest_risk(plan, direction)
    risk_block = _format_risk_block(risk)

    rank_line = f"Rank: {rank}" if rank > 0 else ""
    capital_line = f"Capital: {capital_pct:.0f}%" if capital_pct > 0 else ""
    atr_line = f"ATR%: {atr_pct:.2f}" if atr_pct is not None else ""
    meta_lines = [x for x in (rank_line, capital_line, atr_line) if x]
    meta_block = "\n".join(meta_lines)
    if meta_block:
        meta_block = "\n" + meta_block

    msg = f"""SIGNAL
Coin:
{symbol}
Direction:
{dir_line}
Score:
{score}/14{meta_block}
Reason:
{reason_block}
Action:
{action}
Entry:
{plan.entry_low} - {plan.entry_high}
Stop Loss:
{plan.stop_loss}
Take Profit:
{plan.take_profit}{risk_block}"""
    return msg
