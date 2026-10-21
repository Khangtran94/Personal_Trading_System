from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import hashlib
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import platform
import time
from zoneinfo import ZoneInfo

from loguru import logger

from signal_bot.config import get_settings
from signal_bot.exchange.client import BinanceFuturesClient
from signal_bot.main import SignalPipeline
from signal_bot.strategy.entry import EntryPlan
from .engine import EXECUTION_MODEL, Position, advance, precise_plan, quantize
from .market import PublicHistory, MarketAccessStopped, read_only_client_class
from .store import ShadowStore, summary, protect_database

STRATEGY_VERSION='baseline-filters-tick-plans-event-ban-v2'
PublicMarketClient=read_only_client_class(BinanceFuturesClient)
PUBLIC_FIELDS=('active_start','active_end','timezone','cooldown_minutes','score_buy_threshold',
    'score_buy_max','score_sell_threshold','score_sell_max','atr_sl_multiplier','rr_ratio',
    'min_atr_pct','min_batch_same_direction','rank_closeness_ratio','capital_split_mode',
    'enable_ranking','short_min_rsi','short_rank_top1_only','short_loss_streak_ban','short_ban_hours',
    'main_tf','confirm_tf','scan_limit','min_15m_move_pct','kline_limit')


def public_config(settings, entry_minutes, hold_hours, cost_r):
    result={k:getattr(settings,k) for k in PUBLIC_FIELDS}
    result.update(strategy_version=STRATEGY_VERSION,execution_model_version=EXECUTION_MODEL,
                  entry_minutes=entry_minutes,hold_hours=hold_hours,assumed_cost_r=cost_r,
                  source_baseline_commit='89581aa9edf91a1c72ed6e0636f1d270888ddf92')
    source_root=Path(__file__).resolve().parents[1]
    digest=hashlib.sha256()
    for path in sorted(source_root.rglob('*.py')):
        digest.update(path.relative_to(source_root).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    result['source_code_hash']=digest.hexdigest()
    result['python_version']=platform.python_version()
    result['dependency_versions']={}
    for package in ('pandas','numpy','pandas-ta','pydantic-settings','httpx'):
        try:result['dependency_versions'][package]=version(package)
        except PackageNotFoundError:result['dependency_versions'][package]='missing'
    if not all(math.isfinite(v) for v in (entry_minutes,hold_hours,cost_r)):
        raise ValueError('Execution settings must be finite')
    if entry_minutes <= 0 or entry_minutes % 5 or hold_hours <= 0 or (hold_hours*60)%5 or cost_r < 0:
        raise ValueError('Entry/hold windows must be positive multiples of 5 minutes; cost cannot be negative')
    if settings.short_ban_hours < 0 or settings.cooldown_minutes < 0:
        raise ValueError('Cooldown durations cannot be negative')
    return result


class SilentNotifier:
    async def send(self, message):
        raise RuntimeError('Shadow runner must never send notifications')


class PersistentCooldown:
    def __init__(self, store, settings):
        self.store,self.settings=store,settings
    def is_cooling(self,symbol,direction):
        last=self.store.last_signal_ms(symbol,direction)
        return last is not None and time.time()*1000 < last+self.settings.cooldown_minutes*60_000
    def is_short_banned(self,symbol):
        return self.store.short_banned(symbol,self.settings.short_loss_streak_ban,
                                      self.settings.short_ban_hours,int(time.time()*1000))
    def mark(self,symbol,direction):
        pass  # save_candidate is the durable event used by is_cooling.


class ShadowPipeline(SignalPipeline):
    def __init__(self,store,ticks):
        super().__init__(repository=store,notifier=SilentNotifier(),client_factory=PublicMarketClient)
        self.cooldown=PersistentCooldown(store,self.settings)
        self.ticks=ticks

    def build_entry_plan(self,symbol,snapshot,direction):
        tick=self.ticks.get(symbol)
        if not tick or snapshot.ema20 is None or snapshot.atr is None:
            logger.warning('Shadow plan skipped: missing tick or raw indicator values for {}',symbol)
            return None
        try:
            plan=precise_plan(snapshot.ema20,snapshot.atr,direction,self.settings.atr_sl_multiplier,
                              self.settings.rr_ratio,tick)
            return EntryPlan(**plan)
        except ValueError as exc:
            logger.warning('Shadow plan invalid for {}: {}',symbol,exc)
            return None

    async def _emit(self,candidate):
        plan=candidate.plan;config=self.repo.config
        p=Position(candidate.symbol,candidate.direction,int(time.time()*1000),
            quantize((plan.entry_low+plan.entry_high)/2,self.ticks[candidate.symbol]),
            plan.stop_loss,plan.take_profit,self.ticks[candidate.symbol],
            entry_window_ms=int(config['entry_minutes']*60_000),
            hold_ms=int(config['hold_hours']*3_600_000),cost_r=config['assumed_cost_r'])
        p=advance(p,[],p.signal_ms)
        self.repo.save_candidate(p,candidate.score,candidate.reason_text,candidate.rank,candidate.capital_pct)
        self._emitted+=1
        logger.info('SHADOW {} {} state={} tick={} (no Telegram)',p.symbol,p.direction,p.state,p.tick)


async def update_positions(store,history,now_ms):
    for row,p in store.pending():
        try:
            start=p.first_ms if p.next_ms is None else p.next_ms
            end=min(now_ms,p.end_deadline)
            bars=await history.candles(p.symbol,start,end,now_ms)
            store.cache_bars(p.symbol,bars)
            store.update(row['id'],advance(p,bars,now_ms))
        except MarketAccessStopped:
            raise
        except Exception as exc:
            # Preserve cursor and position on transport/schema/OHLC problems.
            p.data_issue=f'{type(exc).__name__}: {exc}'
            store.update(row['id'],p)
            logger.warning('Shadow history incomplete for {} id={}',p.symbol,row['id'])


def active(settings,now=None):
    now=now or datetime.now(ZoneInfo(settings.timezone))
    start=tuple(map(int,settings.active_start.split(':')))
    end=tuple(map(int,settings.active_end.split(':')))
    value=(now.hour,now.minute)
    return start<=value<=end if start<=end else value>=start or value<=end


@contextmanager
def runner_lock(path: Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    stream=open(path,'a+b')
    stream.seek(0)
    if not stream.read(1):
        stream.write(b'0');stream.flush()
    stream.seek(0)
    try:
        if __import__('os').name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise RuntimeError('Another shadow process already owns this database') from None
    try:
        yield
    finally:
        stream.close()  # OS releases the lock on normal exit or crash.


async def run(args):
    settings=get_settings()
    config=public_config(settings,args.entry_minutes,args.hold_hours,args.cost_r)
    protect_database(args.db,args.baseline_db)
    # A read-only legacy path is only checked for isolation; it is never opened for writing.
    with runner_lock(args.db.with_suffix(args.db.suffix+'.lock')):
        store=ShadowStore(args.db,args.baseline_db,config)
        try:
            logger.info('SHADOW paper DB={} strategy={} execution={}',args.db,STRATEGY_VERSION,EXECUTION_MODEL)
            async with PublicMarketClient() as client:
                history=PublicHistory(client)
                # Startup deliberately fails if exchange rules cannot be loaded.
                pipeline=ShadowPipeline(store,await history.ticks())
                while True:
                    try:
                        await update_positions(store,history,int(time.time()*1000))
                        if not args.track_only and active(settings):
                            await pipeline.run_once()
                        if PublicMarketClient.stopped is not None:
                            raise PublicMarketClient.stopped
                        print(json.dumps(summary(args.db),ensure_ascii=False))
                    except MarketAccessStopped:
                        raise
                    except Exception:
                        if args.once:
                            raise
                        logger.exception('Shadow cycle failed; positions and baseline preserved')
                    if args.once:
                        break
                    # asyncio sleep is cancellable; one serial cycle prevents tracker/scan races.
                    await asyncio.sleep(300)
        finally:
            store.close()
