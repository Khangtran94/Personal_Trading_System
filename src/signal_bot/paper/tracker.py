from __future__ import annotations

from datetime import timezone

from loguru import logger

from signal_bot.config import get_settings
from signal_bot.database.models import SignalRecord
from signal_bot.database.repository import SignalRepository
from signal_bot.exchange.client import BinanceFuturesClient
from signal_bot.exchange.models import Candle


class PaperTracker:
    """
    Forward-test open signals against real Binance USDT-M klines.
    Never places orders — only updates SQLite outcomes.
    """

    def __init__(self, max_hold_hours: float = 8.0) -> None:
        self.settings = get_settings()
        self.repo = SignalRepository()
        self.max_hold_hours = max_hold_hours

    async def run_once(self) -> dict:
        open_sigs = self.repo.list_open()
        if not open_sigs:
            logger.info("Paper tracker: no open signals")
            return {"checked": 0, "closed": 0}

        closed = 0
        async with BinanceFuturesClient() as client:
            by_sym: dict[str, list[SignalRecord]] = {}
            for s in open_sigs:
                by_sym.setdefault(s.symbol, []).append(s)

            for symbol, sigs in by_sym.items():
                try:
                    klines = await client.get_klines(symbol, "5m", limit=200)
                except Exception as e:
                    logger.warning(f"Paper tracker klines failed {symbol}: {e}")
                    continue

                for sig in sigs:
                    outcome = self._evaluate(sig, klines)
                    if outcome is None:
                        continue
                    self.repo.mark_closed(sig.id, **outcome)
                    closed += 1

        logger.info(f"Paper tracker: checked={len(open_sigs)} closed={closed}")
        return {"checked": len(open_sigs), "closed": closed}

    def _evaluate(self, sig: SignalRecord, klines: list[Candle]) -> dict | None:
        entry = (sig.entry_low + sig.entry_high) / 2.0
        sl = sig.stop_loss
        tp = sig.take_profit
        risk = abs(entry - sl)
        if risk <= 0:
            return None

        sig_ts = sig.timestamp
        if sig_ts.tzinfo is None:
            sig_ts = sig_ts.replace(tzinfo=timezone.utc)

        future = [c for c in klines if c.open_time > sig_ts]
        if not future:
            return None

        direction = sig.direction
        max_bars = max(1, int(self.max_hold_hours * 60 / 5))

        for c in future[:max_bars]:
            if direction == "LONG":
                hit_sl = c.low <= sl
                hit_tp = c.high >= tp
                if hit_sl:
                    return self._close(sig, entry, sl, c, "LOSS", -1.0)
                if hit_tp:
                    return self._close(sig, entry, tp, c, "WIN", abs(tp - entry) / risk)
            else:
                hit_sl = c.high >= sl
                hit_tp = c.low <= tp
                if hit_sl:
                    return self._close(sig, entry, sl, c, "LOSS", -1.0)
                if hit_tp:
                    return self._close(sig, entry, tp, c, "WIN", abs(entry - tp) / risk)

        if len(future) >= max_bars:
            last = future[max_bars - 1]
            if direction == "LONG":
                r_mult = (last.close - entry) / risk
            else:
                r_mult = (entry - last.close) / risk
            return self._close(sig, entry, last.close, last, "TIMEOUT", r_mult)

        return None

    def _close(
        self,
        sig: SignalRecord,
        entry: float,
        exit_price: float,
        candle: Candle,
        result: str,
        r_multiple: float,
    ) -> dict:
        if entry:
            if sig.direction == "LONG":
                pnl_pct = (exit_price - entry) / entry * 100
            else:
                pnl_pct = (entry - exit_price) / entry * 100
        else:
            pnl_pct = 0.0
        return {
            "result": result,
            "exit_price": float(exit_price),
            "exit_time": candle.close_time,
            "r_multiple": round(float(r_multiple), 4),
            "pnl_pct": round(float(pnl_pct), 4),
        }

    def format_summary(self) -> str:
        s = self.repo.summary()
        lines = [
            "PAPER FORWARD SUMMARY",
            f"  Open:     {s['open']}",
            f"  Closed:   {s['closed']}",
            f"  Wins:     {s['wins']}",
            f"  Losses:   {s['losses']}",
            f"  Timeout:  {s['timeouts']}",
            f"  Win rate: {s['win_rate']}%",
            f"  Avg R:    {s['avg_r']}",
            f"  Sum R:    {s['sum_r']}",
        ]
        return "\n".join(lines)
