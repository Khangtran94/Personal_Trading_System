from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from signal_bot.config import ensure_data_dir, get_settings


class Base(DeclarativeBase):
    pass


class SignalRecord(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # LONG / SHORT
    score: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    entry_low: Mapped[float] = mapped_column(Float)
    entry_high: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Later fill for analysis
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)  # WIN / LOSS / BE
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


def get_engine():
    ensure_data_dir()
    settings = get_settings()
    return create_engine(settings.database_url, echo=False)


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)


SessionLocal = sessionmaker(autocommit=False, autoflush=False)
