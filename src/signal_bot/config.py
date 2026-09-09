from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    # Binance (optional)
    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")

    # Runtime
    active_start: str = Field(default="07:00", alias="ACTIVE_START")
    active_end: str = Field(default="23:00", alias="ACTIVE_END")
    cooldown_minutes: int = Field(default=30, alias="COOLDOWN_MINUTES")
    # LONG range (inclusive): score_buy_threshold .. score_buy_max
    # Example range 10..12 → SCORE_BUY_THRESHOLD=10, SCORE_BUY_MAX=12
    # Set SCORE_BUY_MAX empty / omit to keep old behaviour (no upper cap).
    score_buy_threshold: int = Field(default=10, alias="SCORE_BUY_THRESHOLD")
    score_buy_max: int | None = Field(default=12, alias="SCORE_BUY_MAX")
    # SHORT range (inclusive): score_sell_threshold .. score_sell_max
    # Convention: sell_threshold = more extreme (more negative), sell_max = closer to zero.
    # Example range -12..-10 → SCORE_SELL_THRESHOLD=-12, SCORE_SELL_MAX=-10
    score_sell_threshold: int = Field(default=-12, alias="SCORE_SELL_THRESHOLD")
    score_sell_max: int | None = Field(default=-10, alias="SCORE_SELL_MAX")
    atr_sl_multiplier: float = Field(default=1.5, alias="ATR_SL_MULTIPLIER")
    rr_ratio: float = Field(default=2.0, alias="RR_RATIO")

    # Risk sizing (for suggested margin in Telegram alerts)
    account_equity: float = Field(default=1000.0, alias="ACCOUNT_EQUITY")
    risk_per_trade_pct: float = Field(default=1.0, alias="RISK_PER_TRADE_PCT")
    suggested_leverage: float = Field(default=10.0, alias="SUGGESTED_LEVERAGE")

    database_url: str = Field(default="sqlite:///./data/signals.db", alias="DATABASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Fixed constants
    timezone: str = "Asia/Ho_Chi_Minh"
    main_tf: str = "15m"
    confirm_tf: str = "5m"
    entry_tf: str = "3m"
    scan_limit: int = 50  # top volume candidates
    min_15m_move_pct: float = 2.0
    kline_limit: int = 200  # enough for EMA50 + indicators


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_data_dir() -> Path:
    """Create data/ folder for SQLite if needed."""
    path = Path("data")
    path.mkdir(exist_ok=True)
    return path
