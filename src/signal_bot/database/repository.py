from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
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
