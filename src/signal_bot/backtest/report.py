from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from signal_bot.backtest.simulator import SimulatedTrade


@dataclass
class BacktestReport:
    total_trades: int
    wins: int
    losses: int
    timeouts: int
    win_rate: float
    profit_factor: float
    avg_r: float
    sum_r: float
    max_drawdown_r: float
    long_trades: int
    short_trades: int
    long_win_rate: float
    short_win_rate: float
    by_symbol: dict[str, dict[str, float | int]]


def build_report(trades: list[SimulatedTrade]) -> BacktestReport:
    if not trades:
        return BacktestReport(
            total_trades=0,
            wins=0,
            losses=0,
            timeouts=0,
            win_rate=0.0,
            profit_factor=0.0,
            avg_r=0.0,
            sum_r=0.0,
            max_drawdown_r=0.0,
            long_trades=0,
            short_trades=0,
            long_win_rate=0.0,
            short_win_rate=0.0,
            by_symbol={},
        )

    tp_wins = [t for t in trades if t.exit_reason == "TP"]
    losses = [t for t in trades if t.exit_reason == "SL"]
    timeouts = [t for t in trades if t.exit_reason in ("TIMEOUT", "END")]

    gross_win = sum(t.r_multiple for t in trades if t.r_multiple > 0)
    gross_loss = abs(sum(t.r_multiple for t in trades if t.r_multiple < 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    rs = [t.r_multiple for t in trades]
    sum_r = sum(rs)
    avg_r = sum_r / len(rs)

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    longs = [t for t in trades if t.direction == "LONG"]
    shorts = [t for t in trades if t.direction == "SHORT"]
    long_wr = (sum(1 for t in longs if t.exit_reason == "TP") / len(longs) * 100) if longs else 0.0
    short_wr = (sum(1 for t in shorts if t.exit_reason == "TP") / len(shorts) * 100) if shorts else 0.0

    by_sym: dict[str, list[SimulatedTrade]] = defaultdict(list)
    for t in trades:
        by_sym[t.symbol].append(t)

    by_symbol: dict[str, dict[str, float | int]] = {}
    for sym, ts in sorted(by_sym.items()):
        n = len(ts)
        w = sum(1 for t in ts if t.exit_reason == "TP")
        by_symbol[sym] = {
            "trades": n,
            "wins": w,
            "win_rate": round(w / n * 100, 1) if n else 0.0,
            "sum_r": round(sum(t.r_multiple for t in ts), 2),
            "avg_r": round(sum(t.r_multiple for t in ts) / n, 3) if n else 0.0,
        }

    return BacktestReport(
        total_trades=len(trades),
        wins=len(tp_wins),
        losses=len(losses),
        timeouts=len(timeouts),
        win_rate=round(len(tp_wins) / len(trades) * 100, 2),
        profit_factor=round(pf, 3) if pf != float("inf") else 999.0,
        avg_r=round(avg_r, 4),
        sum_r=round(sum_r, 3),
        max_drawdown_r=round(max_dd, 3),
        long_trades=len(longs),
        short_trades=len(shorts),
        long_win_rate=round(long_wr, 2),
        short_win_rate=round(short_wr, 2),
        by_symbol=by_symbol,
    )


def format_report(report: BacktestReport, days: int, symbols: list[str]) -> str:
    lines = [
        "=" * 52,
        " BACKTEST REPORT (signal simulation, not live PnL)",
        "=" * 52,
        f" Period:        last {days} days",
        f" Symbols:       {', '.join(symbols)}",
        f" Total trades:  {report.total_trades}",
        f" TP wins:       {report.wins}",
        f" SL losses:     {report.losses}",
        f" Timeout/end:   {report.timeouts}",
        f" Win rate (TP): {report.win_rate}%",
        f" Profit factor: {report.profit_factor}",
        f" Avg R:         {report.avg_r}",
        f" Sum R:         {report.sum_r}",
        f" Max DD (R):    {report.max_drawdown_r}",
        f" LONG:          {report.long_trades} trades, WR {report.long_win_rate}%",
        f" SHORT:         {report.short_trades} trades, WR {report.short_win_rate}%",
        "-" * 52,
        " By symbol:",
    ]
    for sym, st in report.by_symbol.items():
        lines.append(
            f"  {sym:12} n={st['trades']:3}  WR={st['win_rate']:5}%  "
            f"sumR={st['sum_r']:+7}  avgR={st['avg_r']:+.3f}"
        )
    lines.append("=" * 52)
    return "\n".join(lines)


def trades_to_rows(trades: list[SimulatedTrade]) -> list[dict]:
    rows = []
    for t in trades:
        rows.append(
            {
                "symbol": t.symbol,
                "direction": t.direction,
                "signal_time": t.signal_time.isoformat(),
                "score": t.score,
                "entry": t.entry,
                "stop_loss": t.stop_loss,
                "take_profit": t.take_profit,
                "exit_time": t.exit_time.isoformat() if t.exit_time else "",
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "r_multiple": t.r_multiple,
                "bars_held": t.bars_held,
            }
        )
    return rows
