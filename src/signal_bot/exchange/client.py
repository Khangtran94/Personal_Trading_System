from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

from signal_bot.config import get_settings
from signal_bot.exchange.models import Candle, Ticker


class BinanceFuturesClient:
    """Public + optional authenticated client for Binance USDT-M Futures only."""

    BASE_URL = "https://fapi.binance.com"
    # Status codes that mean "back off and retry"
    RETRY_STATUS = {418, 429, 403, 503}
    MAX_RETRIES = 5
    BASE_BACKOFF_SEC = 2.0  # 2, 4, 8, 16, 32

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BinanceFuturesClient":
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=20.0,
            headers={
                # Browser-like UA reduces some WAF 418s vs bare bot strings
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Client not started. Use async with BinanceFuturesClient()")
        return self._client

    async def _get(self, path: str, params: dict | None = None) -> Any:
        """GET with exponential backoff on 418/429/403/503."""
        last_exc: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = await self.client.get(path, params=params or {})
                if resp.status_code in self.RETRY_STATUS:
                    wait = self.BASE_BACKOFF_SEC * (2 ** (attempt - 1))
                    # Honour Retry-After if Binance sends it
                    ra = resp.headers.get("Retry-After")
                    if ra and ra.isdigit():
                        wait = max(wait, float(ra))
                    logger.warning(
                        f"Binance {resp.status_code} on {path} "
                        f"(attempt {attempt}/{self.MAX_RETRIES}) – sleep {wait:.0f}s"
                    )
                    await asyncio.sleep(wait)
                    last_exc = httpx.HTTPStatusError(
                        f"{resp.status_code} for {path}",
                        request=resp.request,
                        response=resp,
                    )
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.TransportError as e:
                wait = self.BASE_BACKOFF_SEC * (2 ** (attempt - 1))
                logger.warning(
                    f"Binance network error on {path}: {e} "
                    f"(attempt {attempt}/{self.MAX_RETRIES}) – sleep {wait:.0f}s"
                )
                await asyncio.sleep(wait)
                last_exc = e
        assert last_exc is not None
        raise last_exc

    async def get_klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 200,
        closed_only: bool = True,
    ) -> list[Candle]:
        """
        Fetch klines. Always drop the last (live) candle when closed_only=True
        so indicators use only completed bars.
        """
        raw = await self._get(
            "/fapi/v1/klines",
            {"symbol": symbol.upper(), "interval": interval, "limit": limit},
        )
        candles: list[Candle] = []
        for row in raw:
            open_time = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
            close_time = datetime.fromtimestamp(row[6] / 1000, tz=timezone.utc)
            candles.append(
                Candle(
                    open_time=open_time,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    close_time=close_time,
                    quote_volume=float(row[7]),
                    trades=int(row[8]),
                    is_closed=True,
                )
            )
        if closed_only and len(candles) > 1:
            # Drop the last candle (still forming)
            candles = candles[:-1]
        return candles

    async def get_24h_tickers(self) -> list[Ticker]:
        """All USDT-M Futures 24h tickers, sorted later by volume."""
        raw = await self._get("/fapi/v1/ticker/24hr")
        tickers: list[Ticker] = []
        for item in raw:
            symbol = item["symbol"]
            if not symbol.endswith("USDT"):
                continue
            tickers.append(
                Ticker(
                    symbol=symbol,
                    price=float(item["lastPrice"]),
                    price_change_pct=float(item["priceChangePercent"]),
                    volume=float(item["volume"]),
                    quote_volume=float(item["quoteVolume"]),
                )
            )
        return tickers

    async def get_exchange_info(self) -> list[str]:
        """Return list of TRADING USDT perpetual symbols."""
        data = await self._get("/fapi/v1/exchangeInfo")
        symbols = []
        for s in data.get("symbols", []):
            if (
                s.get("contractType") == "PERPETUAL"
                and s.get("quoteAsset") == "USDT"
                and s.get("status") == "TRADING"
            ):
                symbols.append(s["symbol"])
        return symbols


# Convenience sync helper for quick tests
def get_klines_sync(symbol: str, interval: str = "15m", limit: int = 100) -> list[Candle]:
    async def _run() -> list[Candle]:
        async with BinanceFuturesClient() as client:
            return await client.get_klines(symbol, interval, limit)

    return asyncio.run(_run())
