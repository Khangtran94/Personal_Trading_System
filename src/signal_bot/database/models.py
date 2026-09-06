from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from signal_bot.config import ensure_data_dir, get_settings


class Base(DeclarativeBase):
    pass


class SignalRecord(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[str] = mapped_column(String(10))
    score: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    entry_low: Mapped[float] = mapped_column(Float)
    entry_high: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    r_multiple: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def get_engine():
    ensure_data_dir()
    settings = get_settings()
    return create_engine(settings.database_url, echo=False)


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate_extra_columns(engine)


def _migrate_extra_columns(engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(signals)")).fetchall()
        existing = {r[1] for r in rows}
        alters = []
        if "r_multiple" not in existing:
            alters.append("ALTER TABLE signals ADD COLUMN r_multiple FLOAT")
        if "exit_price" not in existing:
            alters.append("ALTER TABLE signals ADD COLUMN exit_price FLOAT")
        if "exit_time" not in existing:
            alters.append("ALTER TABLE signals ADD COLUMN exit_time DATETIME")
        for stmt in alters:
            conn.execute(text(stmt))
        if alters:
            conn.commit()


SessionLocal = sessionmaker(autocommit=False, autoflush=False)
