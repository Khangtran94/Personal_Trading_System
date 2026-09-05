from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Candle(BaseModel):
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime
    quote_volume: float = 0.0
    trades: int = 0
    is_closed: bool = True


class Ticker(BaseModel):
    symbol: str
    price: float
    price_change_pct: float = 0.0
    volume: float = 0.0
    quote_volume: float = 0.0


class SymbolInfo(BaseModel):
    symbol: str
    base: str
    quote: str = "USDT"
    status: str = "TRADING"
    price_precision: int = 4
    quantity_precision: int = 3


Direction = Literal["LONG", "SHORT"]
SignalSide = Literal["BUY", "SELL", "NEUTRAL"]
