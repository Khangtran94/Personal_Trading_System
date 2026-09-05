from __future__ import annotations

from datetime import datetime, timedelta, timezone

from signal_bot.config import get_settings
from signal_bot.exchange.models import Direction


class CooldownManager:
    """Same-coin + direction cooldown (default 30 min)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._last: dict[str, datetime] = {}

    def _key(self, symbol: str, direction: Direction) -> str:
        return f"{symbol}:{direction}"

    def is_cooling(self, symbol: str, direction: Direction) -> bool:
        key = self._key(symbol, direction)
        last = self._last.get(key)
        if last is None:
            return False
        elapsed = datetime.now(timezone.utc) - last
        return elapsed < timedelta(minutes=self.settings.cooldown_minutes)

    def mark(self, symbol: str, direction: Direction) -> None:
        key = self._key(symbol, direction)
        self._last[key] = datetime.now(timezone.utc)

    def clear(self, symbol: str | None = None) -> None:
        if symbol is None:
            self._last.clear()
        else:
            to_del = [k for k in self._last if k.startswith(f"{symbol}:")]
            for k in to_del:
                del self._last[k]
