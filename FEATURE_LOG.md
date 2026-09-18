# Feature / Algorithm / Assumption Log

Track every meaningful change to filters, ranking, assumptions and how to reproduce / evaluate them.

---

## How to run the bot

```bash
# One-shot scan (recommended while testing)
uv run python -m signal_bot.main --once

# Continuous mode (scans every 3 min during active hours)
uv run python -m signal_bot.main

# Test Telegram connection only
uv run python -m signal_bot.main --test-telegram
```

## How to check quality / backtest

```bash
# Default backtest (top liquid symbols, last 60 days)
uv run python -m signal_bot.backtest

# Custom symbols / period
uv run python -m signal_bot.backtest --symbols BTCUSDT,ETHUSDT,SOLUSDT --days 90

# Faster sampling + write trade log
uv run python -m signal_bot.backtest --step 3 --days 60 --csv data/backtest_60d.csv
```

After a live run, inspect logs for lines containing:
- `Rank LONG:` / `Rank SHORT:`
- `Ranking kept X / dropped Y`
- `SIGNAL emitted: ... rank= ... capital=...%`

---

## Combination test guide (ranking experiments)

All ranking behaviour is controlled by `.env` (or environment variables).  
Change the values, then run `--once` or a backtest.

### Recommended combinations to try

| Case | ENABLE_RANKING | RANK_CLOSENESS_RATIO | CAPITAL_SPLIT_MODE | MIN_BATCH_SAME_DIRECTION | Purpose |
|------|----------------|----------------------|--------------------|--------------------------|---------|
| A (baseline, no ranking) | false | - | - | 2 | Emit every coin that passed filters |
| B (Top-1 only) | true | 1.01 (impossible for Top-2) | any | 2 | Always only Rank 1 (100% capital) |
| C (Top-1+2, strict) | true | 0.80 | 70_30 | 2 | Top-2 only if within ~20% of leader |
| D (Top-1+2, current default) | true | 0.75 | 70_30 | 2 | Top-2 within ~25% of leader, 70/30 split |
| E (Top-1+2, loose) | true | 0.70 | 50_50 | 2 | More aggressive, equal capital |
| F (old batch=3) | true | 0.75 | 70_30 | 3 | Compare with stricter batch filter |

### How to run each case

```bash
# Example: Case D (default)
export ENABLE_RANKING=true
export RANK_CLOSENESS_RATIO=0.75
export CAPITAL_SPLIT_MODE=70_30
export MIN_BATCH_SAME_DIRECTION=2
uv run python -m signal_bot.main --once

# Example: Case A (no ranking)
export ENABLE_RANKING=false
uv run python -m signal_bot.main --once

# Example: Case B (force Top-1 only)
export ENABLE_RANKING=true
export RANK_CLOSENESS_RATIO=1.01
uv run python -m signal_bot.main --once
```

Or edit `.env` and re-run.

---

## Change Log

### 2026-09-18 – Ranking & Capital Allocation layer

**What changed**
- After batch same-direction filter, candidates are ranked **per direction** (LONG / SHORT independent).
- Ranking keys:
  1. ATR% (higher better)
  2. Entry quality = |close − EMA20| / ATR (lower = closer to ideal entry, better)
- Selection:
  - Always take Rank 1 → 100% capital if alone.
  - Take Rank 2 only when `ATR2 >= ATR1 * RANK_CLOSENESS_RATIO` (default 0.75).
  - When both selected → capital split according to `CAPITAL_SPLIT_MODE` (`50_50` or `70_30`).
- Not-selected coins are still logged so we can later compare Selected vs Not-Selected performance.
- Telegram message now shows Rank, Capital %, ATR%.

**New config keys**
- `ENABLE_RANKING` (default true)
- `RANK_CLOSENESS_RATIO` (default 0.75)
- `CAPITAL_SPLIT_MODE` (default 70_30)

**Assumptions**
- Higher ATR% setups have more room to reach the fixed 1:2 RR target.
- Price closer to EMA20 is a cleaner entry (less chase).
- Batch momentum ≥ 2 already provides most of the win-rate lift; ranking is mainly for capital concentration.
- Narrow score window (11–13) makes raw score a weak secondary ranker → entry quality preferred.

**How to verify**
```bash
uv run python -m signal_bot.main --once
# Look for "Rank LONG:" / "Rank SHORT:" and "SIGNAL emitted: ... rank= ... capital=..."
```

---

### 2026-09-13 – ATR% + Batch same-direction filters

- Added `MIN_ATR_PCT` (default 0.5) and `MIN_BATCH_SAME_DIRECTION` (default 3).
- Commit reference: f1e1ab1

---

## Notes for future experiments

- Track win-rate / avg R of **Selected** vs **Not-Selected** groups.
- If Top-2 rarely survives closeness filter → consider lowering ratio or switching to pure Top-1.
- Capital split is informational for the trader (bot is still signal-only); size positions yourself according to the Capital % shown.
