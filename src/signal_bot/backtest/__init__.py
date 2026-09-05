"""Phase 4 – multi-symbol backtesting engine."""

from signal_bot.backtest.engine import run_backtest
from signal_bot.backtest.report import build_report, format_report

__all__ = ["run_backtest", "build_report", "format_report"]
