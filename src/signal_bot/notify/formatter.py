from __future__ import annotations

from signal_bot.exchange.models import Direction
from signal_bot.indicators.signals import SignalResult
from signal_bot.strategy.entry import EntryPlan


def _arrow(side: str) -> str:
    if side == "BUY":
        return "⬆️"
    if side == "SELL":
        return "⬇️"
    return "➖"


def format_signal(
    symbol: str,
    direction: Direction,
    score: int,
    results: list[SignalResult],
    plan: EntryPlan,
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

    msg = f"""SIGNAL
Coin:
{symbol}
Direction:
{dir_line}
Score:
{score}/14
Reason:
{reason_block}
Action:
{action}
Entry:
{plan.entry_low} - {plan.entry_high}
Stop Loss:
{plan.stop_loss}
Take Profit:
{plan.take_profit}"""
    return msg
