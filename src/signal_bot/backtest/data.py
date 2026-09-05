from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from loguru import logger

from signal_bot.exchange.models import Candle

BASE_URL = "https://fapi.binance.com"
MAX_LIMIT = 1500
CACHE_DIR = Path("data/backtest_cache")


def _ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _parse_row(row: list) -> Candle:
    open_time = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
    close_time = datetime.fromtimestamp(row[6] / 1000, tz=timezone.utc)
    return Candle(
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


async def fetch_klines_range(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    *,
    client: httpx.AsyncClient | None = None,
    use_cache: bool = True,
) -> list[Candle]:
    """
    Paginated public klines for [start, end]. Closed candles only.
    Caches under data/backtest_cache/.
    """
    symbol = symbol.upper()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_name = (
        f"{symbol}_{interval}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
    )
    cache_path = CACHE_DIR / cache_name

    if use_cache and cache_path.exists():
        return _load_cache(cache_path)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

    assert client is not None
    candles: list[Candle] = []
    cursor = _ms(start)
    end_ms = _ms(end)

    try:
        while cursor < end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": MAX_LIMIT,
            }
            resp = await client.get("/fapi/v1/klines", params=params)
            resp.raise_for_status()
            raw = resp.json()
            if not raw:
                break
            batch = [_parse_row(r) for r in raw]
            candles.extend(batch)
            last_open = raw[-1][0]
            next_cursor = last_open + 1
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            if len(raw) < MAX_LIMIT:
                break
            await asyncio.sleep(0.15)
    finally:
        if own_client:
            await client.aclose()

    seen: set[datetime] = set()
    unique: list[Candle] = []
    for c in candles:
        if c.open_time in seen:
            continue
        seen.add(c.open_time)
        unique.append(c)
    unique.sort(key=lambda c: c.open_time)

    if use_cache and unique:
        _save_cache(cache_path, unique)
        logger.info(f"Cached {len(unique)} {interval} bars → {cache_path.name}")

    return unique


def _save_cache(path: Path, candles: list[Candle]) -> None:
    lines = [
        "open_time,open,high,low,close,volume,close_time,quote_volume,trades"
    ]
    for c in candles:
        lines.append(
            f"{c.open_time.isoformat()},{c.open},{c.high},{c.low},{c.close},"
            f"{c.volume},{c.close_time.isoformat()},{c.quote_volume},{c.trades}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_cache(path: Path) -> list[Candle]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out: list[Candle] = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 9:
            continue
        out.append(
            Candle(
                open_time=datetime.fromisoformat(parts[0]),
                open=float(parts[1]),
                high=float(parts[2]),
                low=float(parts[3]),
                close=float(parts[4]),
                volume=float(parts[5]),
                close_time=datetime.fromisoformat(parts[6]),
                quote_volume=float(parts[7]),
                trades=int(parts[8]),
                is_closed=True,
            )
        )
    logger.info(f"Loaded cache {path.name} ({len(out)} bars)")
    return out


def default_symbols() -> list[str]:
    """Liquid USDT-M perpetuals for multi-symbol backtests."""
    return [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "ADAUSDT",
        "AVAXUSDT",
        "LINKUSDT",
        "DOTUSDT",
    ]


def period_bounds(days: int) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start, end
