from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_bot.database.models import SessionLocal, SignalRecord, get_engine, init_db
from signal_bot.exchange.models import Direction
from signal_bot.strategy.entry import EntryPlan


class SignalRepository:
    def __init__(self) -> None:
        init_db()
        self.engine = get_engine()
        SessionLocal.configure(bind=self.engine)

    def save(
        self,
        symbol: str,
        direction: Direction,
        score: int,
        reason: str,
        plan: EntryPlan,
    ) -> int:
        with Session(self.engine) as session:
            rec = SignalRecord(
                timestamp=datetime.now(timezone.utc),
                symbol=symbol,
                direction=direction,
                score=score,
                reason=reason,
                entry_low=plan.entry_low,
                entry_high=plan.entry_high,
                stop_loss=plan.stop_loss,
                take_profit=plan.take_profit,
                atr=plan.atr,
            )
            session.add(rec)
            session.commit()
            session.refresh(rec)
            logger.info(f"Saved signal id={rec.id} {symbol} {direction} score={score}")
            return rec.id

    def list_open(self) -> list[SignalRecord]:
        with Session(self.engine) as session:
            stmt = (
                select(SignalRecord)
                .where(SignalRecord.result.is_(None))
                .order_by(SignalRecord.timestamp.asc())
            )
            rows = list(session.scalars(stmt).all())
            session.expunge_all()
            return rows

    def list_closed(self, limit: int = 200) -> list[SignalRecord]:
        with Session(self.engine) as session:
            stmt = (
                select(SignalRecord)
                .where(SignalRecord.result.is_not(None))
                .order_by(SignalRecord.id.desc())
                .limit(limit)
            )
            rows = list(session.scalars(stmt).all())
            session.expunge_all()
            return rows

    def mark_closed(
        self,
        signal_id: int,
        *,
        result: str,
        exit_price: float,
        exit_time: datetime,
        r_multiple: float,
        pnl_pct: float,
    ) -> None:
        with Session(self.engine) as session:
            rec = session.get(SignalRecord, signal_id)
            if rec is None:
                return
            rec.result = result
            rec.exit_price = exit_price
            rec.exit_time = exit_time
            rec.r_multiple = r_multiple
            rec.pnl_pct = pnl_pct
            session.commit()
            logger.info(
                f"Paper close id={signal_id} {rec.symbol} {rec.direction} "
                f"{result} R={r_multiple:+.2f}"
            )

    def summary(self) -> dict:
        closed = self.list_closed(limit=10_000)
        open_n = len(self.list_open())
        if not closed:
            return {
                "open": open_n,
                "closed": 0,
                "wins": 0,
                "losses": 0,
                "timeouts": 0,
                "win_rate": 0.0,
                "avg_r": 0.0,
                "sum_r": 0.0,
            }
        wins = [c for c in closed if c.result == "WIN"]
        losses = [c for c in closed if c.result == "LOSS"]
        timeouts = [c for c in closed if c.result == "TIMEOUT"]
        rs = [c.r_multiple for c in closed if c.r_multiple is not None]
        sum_r = sum(rs) if rs else 0.0
        avg_r = sum_r / len(rs) if rs else 0.0
        return {
            "open": open_n,
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "timeouts": len(timeouts),
            "win_rate": round(len(wins) / len(closed) * 100, 2),
            "avg_r": round(avg_r, 4),
            "sum_r": round(sum_r, 3),
        }
