from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from .engine import Position, TERMINAL


def fingerprint(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def protect_database(path: Path, baseline: Path):
    path, baseline = path.resolve(), baseline.resolve()
    if not baseline.is_file():
        raise ValueError("--baseline-db must identify the existing baseline database")
    if path == baseline or (path.exists() and path.samefile(baseline)):
        raise ValueError("Shadow database must be different from the baseline database")
    if path.exists():
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "signals" in tables or (tables and "validation_meta" not in tables):
                raise ValueError("Refusing to write into a legacy or unrelated database")


class ShadowStore:
    def __init__(self, path: Path, baseline: Path, config: dict):
        protect_database(path, baseline)
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript('''
            CREATE TABLE IF NOT EXISTS validation_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS positions (
              id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, direction TEXT NOT NULL,
              signal_ms INTEGER NOT NULL, score INTEGER NOT NULL, reason TEXT NOT NULL,
              strategy_version TEXT NOT NULL, execution_model_version TEXT NOT NULL,
              config_hash TEXT NOT NULL, rank INTEGER NOT NULL, capital_pct REAL NOT NULL,
              position_json TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS positions_symbol ON positions(symbol,direction);
            CREATE TABLE IF NOT EXISTS candles (
              symbol TEXT NOT NULL, open_ms INTEGER NOT NULL, o REAL NOT NULL, h REAL NOT NULL,
              l REAL NOT NULL, c REAL NOT NULL, PRIMARY KEY(symbol,open_ms));
        ''')
        self.hash = fingerprint(config)
        prior = self.con.execute("SELECT value FROM validation_meta WHERE key='config_hash'").fetchone()
        if prior and prior[0] != self.hash:
            self.con.close()
            raise ValueError("Configuration/version changed. Use a new shadow database for this cohort")
        self.config = config
        for key, value in {"config_hash":self.hash, "config":json.dumps(config,sort_keys=True),
                           "schema_version":"1", "baseline_path":str(baseline.resolve())}.items():
            self.con.execute("INSERT OR IGNORE INTO validation_meta VALUES (?,?)", (key,value))
        self.con.commit()

    def save_candidate(self, p: Position, score: int, reason: str, rank: int, capital_pct: float):
        with self.con:
            self.con.execute('''INSERT INTO positions
                (symbol,direction,signal_ms,score,reason,strategy_version,execution_model_version,
                 config_hash,rank,capital_pct,position_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (p.symbol,p.direction,p.signal_ms,score,reason,self.config['strategy_version'],
                 self.config['execution_model_version'],self.hash,rank,capital_pct,
                 json.dumps(asdict(p),allow_nan=False)))

    def all(self):
        return [(r,Position(**json.loads(r['position_json'])))
                for r in self.con.execute("SELECT * FROM positions ORDER BY id")]

    def pending(self):
        return [(r,p) for r,p in self.all() if p.state not in TERMINAL]

    def update(self, id: int, p: Position):
        with self.con:
            self.con.execute("UPDATE positions SET position_json=? WHERE id=?",
                             (json.dumps(asdict(p),allow_nan=False),id))

    def cache_bars(self, symbol, bars):
        with self.con:
            for b in bars:
                old = self.con.execute("SELECT o,h,l,c FROM candles WHERE symbol=? AND open_ms=?",
                                       (symbol,b.open_ms)).fetchone()
                values = (b.open,b.high,b.low,b.close)
                if old and tuple(old) != values:
                    raise ValueError(f"Historical OHLC changed for {symbol} at {b.open_ms}; review required")
                self.con.execute("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?)",
                                 (symbol,b.open_ms,*values))

    def last_signal_ms(self, symbol, direction):
        row=self.con.execute("SELECT MAX(signal_ms) FROM positions WHERE symbol=? AND direction=?",
                             (symbol,direction)).fetchone()
        return row[0]

    def short_banned(self, symbol, needed, hours, now_ms):
        if needed <= 0:
            return False
        closed = [(r,p) for r,p in self.all() if p.symbol == symbol and p.direction == 'SHORT'
                  and p.state in {'WIN','LOSS','TIMEOUT'}]
        closed.sort(key=lambda rp:(rp[1].exit_ms,rp[0]['id']),reverse=True)
        if len(closed) < needed or any(p.state != 'LOSS' for _,p in closed[:needed]):
            return False
        # Anchor to the loss event, never to each fresh scan. Restart-safe.
        return now_ms < closed[0][1].exit_ms + hours * 3_600_000

    def close(self):
        self.con.close()


def read_positions(path: Path):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro',uri=True) as con:
        con.row_factory=sqlite3.Row
        meta=dict(con.execute('SELECT key,value FROM validation_meta'))
        rows=[(dict(r),Position(**json.loads(r['position_json'])))
              for r in con.execute('SELECT * FROM positions ORDER BY id')]
        return meta,rows


def summary(path: Path) -> dict:
    meta,rows=read_positions(path)
    states={}
    for _,p in rows:
        states[p.state]=states.get(p.state,0)+1
    closed=sorted([p for _,p in rows if p.state in {'WIN','LOSS','TIMEOUT'}],
                  key=lambda p:(p.exit_ms,p.signal_ms))
    rs=[p.net_r for p in closed]
    e=peak=dd=0.0
    for r in rs:
        e+=r;peak=max(peak,e);dd=max(dd,peak-e)
    positive=sum(r for r in rs if r>0);negative=-sum(r for r in rs if r<0)
    return {'states':states,'closed_filled':len(closed),'target':700,
            'remaining':max(0,700-len(closed)),
            'gross_sum_r':sum(p.r_multiple for p in closed),
            'assumed_net_sum_r':sum(rs),'assumed_net_avg_r':sum(rs)/len(rs) if rs else None,
            'assumed_net_pf':positive/negative if negative else ('infinity' if positive else None),
            'closed_trade_net_drawdown_r':dd,'data_issues':sum(bool(p.data_issue) for _,p in rows),
            'config':json.loads(meta['config'])}


def export_rows(path: Path):
    _,rows=read_positions(path)
    iso=lambda ms:datetime.fromtimestamp(ms/1000,timezone.utc).isoformat() if ms is not None else ''
    for r,p in rows:
        yield dict(id=r['id'],symbol=p.symbol,direction=p.direction,signal_time=iso(p.signal_ms),
                   fill_time=iso(p.fill_ms),exit_time=iso(p.exit_ms),result=p.state,
                   r_multiple=p.r_multiple,net_r=p.net_r,assumed_cost_r=p.cost_r,
                   strategy_version=r['strategy_version'],execution_model_version=r['execution_model_version'],
                   config_hash=r['config_hash'],note=p.note,data_issue=p.data_issue)
