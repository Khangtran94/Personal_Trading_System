from __future__ import annotations

from loguru import logger

from signal_bot.config import get_settings
from signal_bot.exchange.client import BinanceFuturesClient
from signal_bot.exchange.models import Ticker


class VolumeScanner:
    """
    Scan top USDT-M Futures by quote volume.
    Keep only coins with 15m absolute move > min_15m_move_pct (default 2%).
    """

    def __init__(self, client: BinanceFuturesClient) -> None:
        self.client = client
        self.settings = get_settings()

    async def scan(self) -> list[str]:
        tickers = await self.client.get_24h_tickers()
        # Sort by quote volume descending
        tickers.sort(key=lambda t: t.quote_volume, reverse=True)

        candidates = tickers[: self.settings.scan_limit]
        selected: list[str] = []

        for t in candidates:
            # Quick 15m move check using last closed 15m candle change
            # For speed we use 24h change as proxy first; refine with real klines if needed
            if abs(t.price_change_pct) < self.settings.min_15m_move_pct:
                # Still check recent 15m volatility more accurately
                try:
                    klines = await self.client.get_klines(t.symbol, "15m", limit=5)
                    if len(klines) < 2:
                        continue
                    last = klines[-1]
                    prev = klines[-2]
                    move_pct = abs((last.close - prev.close) / prev.close) * 100
                    if move_pct < self.settings.min_15m_move_pct:
                        continue
                except Exception as e:
                    logger.debug(f"Skip {t.symbol} kline check: {e}")
                    continue

            selected.append(t.symbol)

        logger.info(f"Scanner selected {len(selected)} symbols from top {self.settings.scan_limit}")
        return selected
