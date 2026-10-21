import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from signal_bot.validation.engine import Bar, Position, BAR_MS, advance, precise_plan, quantize
from signal_bot.validation.market import PublicHistory
from signal_bot.validation.store import ShadowStore, protect_database, summary, export_rows

T=1_800_000_000_000
assert T % BAR_MS == 0


def pos(**kwargs):
    return replace(Position('TESTUSDT','LONG',T-1,100,98,105,'0.1'),**kwargs)


def bar(i=0,o=101,h=102,l=99,c=101):
    return Bar(T+i*BAR_MS,o,h,l,c)


def test_limit_must_fill_before_any_target_is_scored():
    p=advance(pos(entry_window_ms=BAR_MS),[bar(o=104,h=106,l=103,c=105)],T+BAR_MS)
    assert p.state=='UNFILLED' and p.r_multiple is None


def test_same_candle_entry_target_is_review_instead_of_invented_win():
    p=advance(pos(),[bar(h=106)],T+BAR_MS)
    assert p.state=='REVIEW' and p.r_multiple is None


def test_same_candle_entry_stop_is_pessimistic_loss():
    p=advance(pos(),[bar(l=97,h=106)],T+BAR_MS)
    assert p.state=='LOSS' and p.r_multiple==-1 and p.net_r==-1.05


def test_later_target_after_observed_fill():
    p=advance(pos(),[bar(),bar(1,o=102,h=106,l=101,c=105)],T+2*BAR_MS)
    assert p.state=='WIN' and p.r_multiple==2.5 and p.net_r==2.45


def test_marketable_limit_fills_at_better_open_and_recomputes_risk():
    p=advance(pos(),[bar(o=99,h=106,l=98.5,c=105)],T+BAR_MS)
    assert p.state=='WIN' and p.fill_price==99 and p.r_multiple==6


def test_gap_through_entry_and_stop_needs_review():
    p=advance(pos(),[bar(o=97,h=101,l=96,c=100)],T+BAR_MS)
    assert p.state=='REVIEW' and p.r_multiple is None


def test_gap_through_stop_after_fill_can_lose_more_than_one_r():
    p=advance(pos(),[bar(),bar(1,o=96,h=97,l=95,c=96)],T+2*BAR_MS)
    assert p.state=='LOSS' and p.exit_price==96 and p.r_multiple==-2


def test_timeout_uses_fill_window_and_keeps_actual_return():
    p=advance(pos(hold_ms=2*BAR_MS),[bar(),bar(1,o=101,h=102,l=99,c=101)],T+2*BAR_MS)
    assert p.state=='TIMEOUT' and p.r_multiple==.5


@pytest.mark.parametrize('direction,entry,stop,target,o,h,l,c,expected',[
    ('SHORT',100,102,95,99,101,98,99,'OPEN'),
    ('SHORT',100,102,95,99,101,94,96,'REVIEW'),
    ('SHORT',100,102,95,99,103,94,100,'LOSS'),
    ('SHORT',100,102,95,101,101.5,94,96,'WIN'),
])
def test_short_symmetry(direction,entry,stop,target,o,h,l,c,expected):
    p=advance(pos(direction=direction,entry=entry,stop=stop,target=target),[bar(o=o,h=h,l=l,c=c)],T+BAR_MS)
    assert p.state==expected


def test_missing_first_bar_never_infers_outcomes_from_recent_window():
    p=advance(pos(),[bar(2,h=106)],T+3*BAR_MS)
    assert p.state=='PENDING_ENTRY' and p.fill_ms is None and p.next_ms is None
    assert 'Missing' in p.data_issue


def test_gap_blocks_progress_and_can_be_backfilled_idempotently():
    first=advance(pos(),[bar(),bar(2,h=106)],T+3*BAR_MS)
    assert first.state=='OPEN' and first.next_ms==T+BAR_MS and first.data_issue
    recovered=advance(first,[bar(),bar(1),bar(2,h=106)],T+3*BAR_MS)
    assert recovered.state=='WIN' and recovered.data_issue==''
    assert advance(recovered,[bar(2,h=106)],T+4*BAR_MS)==recovered


def test_no_live_or_pre_signal_candle_is_used():
    p=advance(pos(signal_ms=T+1),[bar(h=106),bar(1,h=106)],T+BAR_MS+10)
    assert p.fill_ms is None and p.state=='PENDING_ENTRY'


@pytest.mark.parametrize('patch',[{'stop':100},{'entry':float('nan')},{'tick':'0'},
    {'direction':'INVALID'},{'target':99},{'entry_window_ms':1},{'hold_ms':0}])
def test_invalid_plan_is_terminal_and_unscored(patch):
    p=advance(pos(**patch),[],T)
    assert p.state=='INVALID' and p.r_multiple is None


def test_invalid_ohlc_is_flagged_not_scored():
    p=advance(pos(),[bar(o=100,h=99,l=98,c=100)],T+BAR_MS)
    assert p.data_issue and p.next_ms is None


def test_low_price_plan_uses_symbol_tick_without_zero_risk_rounding():
    p=precise_plan(.0017,.0000123,'LONG',1.5,2,'0.0000001')
    entry=quantize((p['entry_low']+p['entry_high'])/2,'0.0000001')
    assert p['stop_loss'] < entry < p['take_profit']
    assert p['atr']==.0000123
    assert p['entry_low'] != round(p['entry_low'],4)


def setup_store(tmp_path):
    legacy=tmp_path/'legacy.db'
    with sqlite3.connect(legacy) as con:
        con.execute('CREATE TABLE signals(id INTEGER)');con.execute('INSERT INTO signals VALUES (381)')
    config={'strategy_version':'test-s1','execution_model_version':'test-e2','cost':.05}
    return legacy,ShadowStore(tmp_path/'shadow.db',legacy,config),config


def test_baseline_is_unchanged_and_aliases_are_rejected(tmp_path):
    legacy,store,_=setup_store(tmp_path)
    before=hashlib.sha256(legacy.read_bytes()).hexdigest()
    store.save_candidate(pos(),-12,'test',1,100)
    store.update(1,advance(pos(),[bar(),bar(1,h=106)],T+2*BAR_MS))
    assert summary(store.path)['closed_filled']==1
    assert list(export_rows(store.path))[0]['r_multiple']==2.5
    assert hashlib.sha256(legacy.read_bytes()).hexdigest()==before
    with pytest.raises(ValueError,match='different'):protect_database(legacy,legacy)
    alias=tmp_path/'alias.db';alias.hardlink_to(legacy)
    with pytest.raises(ValueError,match='different'):protect_database(alias,legacy)
    store.close()


def test_refuse_other_legacy_db_and_changed_cohort(tmp_path):
    legacy,store,config=setup_store(tmp_path);path=store.path;store.close()
    other=tmp_path/'other.db'
    with sqlite3.connect(other) as con:con.execute('CREATE TABLE signals(id INTEGER)')
    with pytest.raises(ValueError,match='legacy'):ShadowStore(other,legacy,config)
    with pytest.raises(ValueError,match='changed'):ShadowStore(path,legacy,{**config,'cost':.1})


def test_ban_expires_from_exit_event_and_does_not_rearm_after_restart(tmp_path):
    legacy,store,config=setup_store(tmp_path)
    for i in range(2):
        p=pos(direction='SHORT',stop=102,target=95,signal_ms=T+i*BAR_MS,
              state='LOSS',fill_ms=T,fill_price=100,exit_ms=T+(i+1)*BAR_MS,
              exit_price=102,r_multiple=-1,net_r=-1.05)
        store.save_candidate(p,-12,'test',1,100)
    anchor=T+2*BAR_MS
    assert store.short_banned('TESTUSDT',2,8,anchor+1000)
    assert not store.short_banned('TESTUSDT',2,8,anchor+8*3_600_000)
    path=store.path;store.close();store=ShadowStore(path,legacy,config)
    assert not store.short_banned('TESTUSDT',2,8,anchor+10*3_600_000)
    store.close()


def test_unfilled_invalid_and_review_never_count_towards_700(tmp_path):
    _,store,_=setup_store(tmp_path)
    for state in ['INVALID','UNFILLED','REVIEW','PENDING_ENTRY','OPEN']:
        store.save_candidate(pos(state=state),12,'test',1,100)
    assert summary(store.path)['closed_filled']==0
    assert summary(store.path)['remaining']==700
    store.close()


def test_cached_historical_candle_cannot_silently_change(tmp_path):
    _,store,_=setup_store(tmp_path)
    store.cache_bars('TESTUSDT',[bar()]);store.cache_bars('TESTUSDT',[bar()])
    with pytest.raises(ValueError,match='changed'):store.cache_bars('TESTUSDT',[bar(c=100)])
    store.close()


def raw(i):
    return [T+i*BAR_MS,'101','102','99','101','0',T+(i+1)*BAR_MS-1]


def test_historical_fetch_paginates_and_keeps_last_closed_historical_candle():
    class FakeClient:
        def __init__(self):self.calls=[]
        async def _get(self,path,params):
            assert path=='/fapi/v1/klines'
            self.calls.append(params)
            first=(params['startTime']-T)//BAR_MS
            return [raw(i) for i in range(first,min(first+1000,1002))]
    client=FakeClient()
    bars=asyncio.run(PublicHistory(client).candles('TESTUSDT',T,T+1002*BAR_MS,T+1002*BAR_MS))
    assert len(bars)==1002 and len(client.calls)==2 and bars[-1].open_ms==T+1001*BAR_MS


def test_shadow_pipeline_cannot_construct_legacy_db_or_send_telegram(tmp_path,monkeypatch):
    import signal_bot.main as main
    from signal_bot.validation.runner import ShadowPipeline,public_config,runner_lock
    from signal_bot.config import get_settings
    from signal_bot.strategy.entry import EntryPlan
    from signal_bot.strategy.market_filter import SignalCandidate
    def forbidden(*args,**kwargs):raise AssertionError('Legacy DB or notifier was constructed')
    monkeypatch.setattr(main,'SignalRepository',forbidden)
    monkeypatch.setattr(main,'TelegramNotifier',forbidden)
    legacy,store,_=setup_store(tmp_path)
    # Use the same fixed execution options expected by the runner.
    store.config.update(entry_minutes=60,hold_hours=8,assumed_cost_r=.05)
    pipeline=ShadowPipeline(store,{'TESTUSDT':'0.1'})
    candidate=SignalCandidate('TESTUSDT','LONG',11,[],EntryPlan(99.9,100.1,98,105,.5),'test',.5)
    asyncio.run(pipeline._emit(candidate))
    assert len(store.all())==1
    public=public_config(get_settings(),60,8,.05)
    assert not any('token' in k or 'secret' in k or 'api_key' in k for k in public)
    with runner_lock(tmp_path/'runner.lock'):
        with pytest.raises(RuntimeError,match='Another'):
            with runner_lock(tmp_path/'runner.lock'):pass
    store.close()


def test_legacy_entry_hook_is_unchanged(monkeypatch):
    from signal_bot.main import SignalPipeline
    sentinel=object()
    class Calculator:
        def zone(self,snapshot,direction):return sentinel
    pipeline=object.__new__(SignalPipeline);pipeline.entry_calc=Calculator()
    assert pipeline.build_entry_plan('ANY',object(),'LONG') is sentinel


def test_tracker_network_error_preserves_position_cursor(tmp_path):
    from signal_bot.validation.runner import update_positions
    _,store,_=setup_store(tmp_path);store.save_candidate(pos(),11,'test',1,100)
    class Broken:
        async def candles(self,*args):raise OSError('fixture unavailable')
    asyncio.run(update_positions(store,Broken(),T+BAR_MS))
    p=store.all()[0][1]
    assert p.state=='PENDING_ENTRY' and p.next_ms is None and 'unavailable' in p.data_issue
    store.close()


def test_legacy_and_corrected_engine_on_same_no_fill_fixture():
    from datetime import datetime,timezone
    from types import SimpleNamespace
    from signal_bot.paper.tracker import PaperTracker
    from signal_bot.exchange.models import Candle
    signal=SimpleNamespace(entry_low=99.9,entry_high=100.1,stop_loss=98,take_profit=105,
        direction='LONG',timestamp=datetime.fromtimestamp((T-1)/1000,timezone.utc))
    candle=Candle(open_time=datetime.fromtimestamp(T/1000,timezone.utc),open=104,high=106,
        low=103,close=105,volume=1,close_time=datetime.fromtimestamp((T+BAR_MS-1)/1000,timezone.utc))
    legacy=object.__new__(PaperTracker);legacy.max_hold_hours=8
    old=legacy._evaluate(signal,[candle])
    new=advance(pos(entry_window_ms=BAR_MS),[bar(o=104,h=106,l=103,c=105)],T+BAR_MS)
    assert old['result']=='WIN' and old['r_multiple']==2.5
    assert new.state=='UNFILLED' and new.r_multiple is None


def test_shadow_client_denies_non_market_endpoints_and_does_not_retry_rate_limit():
    from signal_bot.validation.market import read_only_client_class,MarketAccessStopped
    class Base:pass
    Client=read_only_client_class(Base)
    c=Client()
    class Fake:
        calls=0
        async def get(self,*args,**kwargs):
            self.calls+=1
            return type('Response',(),{'status_code':429,'headers':{'Retry-After':'4000'}})()
    c.client=Fake()
    with pytest.raises(ValueError,match='public'):asyncio.run(c._get('/fapi/v1/order'))
    assert c.client.calls==0
    with pytest.raises(MarketAccessStopped,match='4000'):asyncio.run(c._get('/fapi/v1/klines'))
    assert c.client.calls==1
    other=Client();other.client=Fake()
    with pytest.raises(MarketAccessStopped,match='4000'):asyncio.run(other._get('/fapi/v1/exchangeInfo'))
    assert other.client.calls==0
