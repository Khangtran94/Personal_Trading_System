from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path
import sys

from .store import export_rows, summary


def main():
    p=argparse.ArgumentParser(description='Isolated paper shadow; public data only, no orders or Telegram')
    p.add_argument('--db',type=Path,default=Path('data/paper_v2.db'))
    p.add_argument('--baseline-db',type=Path,help='Existing original DB; required for a paper run')
    p.add_argument('--once',action='store_true',help='One paper/scan cycle, then exit')
    p.add_argument('--track-only',action='store_true',help='Update existing shadow positions without new signals')
    p.add_argument('--summary',action='store_true',help='Read-only summary; no network')
    p.add_argument('--export-csv',type=Path,help='Export shadow records; no network')
    p.add_argument('--export-all',action='store_true',help='Include unfilled/invalid/review/open states for audit')
    p.add_argument('--entry-minutes',type=int,default=60)
    p.add_argument('--hold-hours',type=float,default=8)
    p.add_argument('--cost-r',type=float,default=.05,help='Assumed total cost drag per filled trade in R, not measured fees')
    args=p.parse_args()
    try:
        if args.summary:
            print(json.dumps(summary(args.db),ensure_ascii=False,indent=2))
            return
        if args.export_csv:
            if args.export_csv.resolve()==args.db.resolve() or (args.export_csv.exists() and args.export_csv.samefile(args.db)):
                p.error('Export path must not overwrite the database')
            if args.export_csv.exists():
                p.error('Export file already exists; choose a new filename')
            rows=list(export_rows(args.db))
            if not args.export_all:
                rows=[r for r in rows if r['result'] in {'WIN','LOSS','TIMEOUT'}]
            if not rows:
                p.error('No shadow records to export')
            args.export_csv.parent.mkdir(parents=True,exist_ok=True)
            with args.export_csv.open('x',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
            return
        if args.baseline_db is None:
            p.error('--baseline-db is required to protect the original dataset')
        from .runner import run
        asyncio.run(run(args))
    except (ValueError,RuntimeError,OSError) as exc:
        p.exit(2,f'Validation stopped: {exc}\n')
    except KeyboardInterrupt:
        print('Shadow stopped. Baseline remains independent.')


if __name__=='__main__':
    main()
