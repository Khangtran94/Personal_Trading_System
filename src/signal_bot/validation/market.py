from __future__ import annotations

from .engine import Bar, BAR_MS


class MarketAccessStopped(RuntimeError):
    """Stop the paper process on rate limiting or blocked access; do not retry around it."""


def read_only_client_class(base):
    class ReadOnlyClient(base):
        stopped = None  # Shared by scanner/history clients for this process.
        async def _get(self,path,params=None):
            if ReadOnlyClient.stopped is not None:
                raise ReadOnlyClient.stopped
            if path not in {'/fapi/v1/klines','/fapi/v1/exchangeInfo','/fapi/v1/ticker/24hr'}:
                raise ValueError('Shadow client permits public market-data endpoints only')
            response=await self.client.get(path,params=params or {})
            if response.status_code in {403,418,429}:
                ReadOnlyClient.stopped = MarketAccessStopped(
                    f'Public market access stopped ({response.status_code}); '
                    f'Retry-After={response.headers.get("Retry-After","unspecified")}. '
                    'Stop this run and follow the provider limit before restarting.')
                raise ReadOnlyClient.stopped
            response.raise_for_status()
            return response.json()
    return ReadOnlyClient


class PublicHistory:
    """Only unsigned public GET endpoints through the existing public client."""
    def __init__(self, client):
        self.client=client

    async def ticks(self):
        data=await self.client._get('/fapi/v1/exchangeInfo')
        return {s['symbol']:next(f['tickSize'] for f in s['filters'] if f['filterType']=='PRICE_FILTER')
                for s in data['symbols'] if s.get('status')=='TRADING'
                and s.get('contractType')=='PERPETUAL' and s.get('quoteAsset')=='USDT'}

    async def candles(self, symbol, start_ms, end_ms, now_ms):
        bars=[];cursor=start_ms
        while cursor < end_ms and cursor + BAR_MS <= now_ms:
            raw=await self.client._get('/fapi/v1/klines',dict(symbol=symbol,interval='5m',
                startTime=cursor,endTime=end_ms-1,limit=1000))
            if not raw:
                break
            for r in raw:
                if int(r[0]) >= cursor and int(r[6]) < now_ms and int(r[0])+BAR_MS <= end_ms:
                    bars.append(Bar(int(r[0]),float(r[1]),float(r[2]),float(r[3]),float(r[4])))
            next_cursor=int(raw[-1][0])+BAR_MS
            if next_cursor <= cursor:
                raise ValueError('History endpoint did not advance its candle cursor')
            cursor=next_cursor
            if len(raw)<1000:
                break
        return bars
