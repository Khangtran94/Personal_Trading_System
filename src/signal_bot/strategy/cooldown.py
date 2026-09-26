from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger

from signal_bot.config import get_settings
from signal_bot.exchange.models import Direction


class CooldownManager:
    """
    Same-coin + direction cooldown (default 30 min) plus
    SHORT loss-streak ban (2 consecutive SHORT losses → 8 h ban).
    """

    def __init__(self, repo=None) -> None:
        self.settings = get_settings()
        self._last: dict[str, datetime] = {}
        # Optional SignalRepository for loss-streak checks (lazy-bound from pipeline)
        self._repo = repo
        # In-memory SHORT ban until (symbol → ban_until_utc)
        self._short_ban_until: dict[str, datetime] = {}

    def bind_repo(self, repo) -> None:
        """Attach the signal repository so loss-streak can query closed trades."""
        self._repo = repo

    def _key(self, symbol: str, direction: Direction) -> str:
        return f"{symbol}:{direction}"

    def is_cooling(self, symbol: str, direction: Direction) -> bool:
        """Normal per-signal cooldown (default 30 min after emit)."""
        key = self._key(symbol, direction)
        last = self._last.get(key)
        if last is None:
            return False
        elapsed = datetime.now(timezone.utc) - last
        return elapsed < timedelta(minutes=self.settings.cooldown_minutes)

    def is_short_banned(self, symbol: str) -> bool:
        """
        True when this symbol is under an active SHORT loss-streak ban.
        Also refreshes the ban from DB if needed.
        """
        if self.settings.short_loss_streak_ban <= 0:
            return False

        now = datetime.now(timezone.utc)

        # Fast path: already banned in memory
        until = self._short_ban_until.get(symbol)
        if until is not None:
            if now < until:
                return True
            # Ban expired
            del self._short_ban_until[symbol]

        # Check recent closed SHORT results from DB
        if self._repo is None:
            return False

        streak = self._repo.count_consecutive_short_losses(symbol)
        needed = self.settings.short_loss_streak_ban
        if streak >= needed:
            ban_hours = self.settings.short_ban_hours
            ban_until = now + timedelta(hours=ban_hours)
            self._short_ban_until[symbol] = ban_until
            logger.info(
                f"SHORT ban activated: {symbol} has {streak} consecutive SHORT losses "
                f"→ banned for {ban_hours:.0f}h (until {ban_until.isoformat()})"
            )
            return True
        return False

    def mark(self, symbol: str, direction: Direction) -> None:
        key = self._key(symbol, direction)
        self._last[key] = datetime.now(timezone.utc)

    def clear(self, symbol: str | None = None) -> None:
        if symbol is None:
            self._last.clear()
            self._short_ban_until.clear()
        else:
            to_del = [k for k in self._last if k.startswith(f"{symbol}:")]
            for k in to_del:
                del self._last[k]
            self._short_ban_until.pop(symbol, None)
