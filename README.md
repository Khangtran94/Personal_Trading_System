# Personal Trading System – Binance USDT-M Futures Signal Bot

**SIGNAL-ONLY** bot. It never places trades.  
You receive clean LONG / SHORT alerts on Telegram and decide yourself.

## Features (v0.1)

- Scans top volume USDT-M Futures
- Filters coins with ≥ 2 % recent 15m move
- 8 indicators + ATR (EMA, Supertrend, MACD DIF, Volume, RSI, KDJ, StochRSI, Williams %R)
- Strict scoring (−14 … +14) → only ≥ +10 (LONG) or ≤ −10 (SHORT)
- 15m trend gate (EMA + Supertrend must agree)
- RSI protection (no LONG when RSI > 80, no SHORT when RSI < 20)
- Entry zone around EMA20 ± ATR, SL = 1.5 × ATR, TP = 1:2 RR
- 30-minute same-coin cooldown
- Active hours 07:00–23:00 Asia/Ho_Chi_Minh
- All signals stored in SQLite for later analysis
- Closed candles only (backtest-friendly)

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/Khangtran94/Personal_Trading_System.git
cd Personal_Trading_System
uv sync          # or: pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env → put your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
```

How to get Telegram credentials:
1. Talk to @BotFather → create a bot → copy token
2. Start a chat with your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your `chat.id`

### 3. Run once (test)

```bash
uv run python -m signal_bot.main --once
```

### 4. Run continuously

```bash
uv run python -m signal_bot.main
```

The bot scans every 3 minutes during active hours.

## Backtest (Phase 4a)

Public Binance data only — **no API key required**.

```bash
# Default: 10 liquid symbols, last 60 days
uv run python -m signal_bot.backtest

# Custom symbols / period
uv run python -m signal_bot.backtest --symbols BTCUSDT,ETHUSDT,SOLUSDT --days 90

# Faster sampling (every 3rd 5m bar ≈ 15m cadence)
uv run python -m signal_bot.backtest --step 3 --days 60

# Write trade log
uv run python -m signal_bot.backtest --csv data/backtest_60d.csv
```

Klines are cached under `data/backtest_cache/` for re-runs.

## Project Layout

```
src/signal_bot/
├── exchange/       # Binance USDT-M client (public data)
├── scanner/        # Top-volume + volatility filter
├── indicators/     # 8 indicators + ATR
├── strategy/       # Trend filter, scorer, entry, cooldown
├── notify/         # Telegram formatter + notifier
├── database/       # SQLite signal storage
├── backtest/       # Multi-symbol walk-forward engine
├── config.py
├── scheduler.py
└── main.py
```

## Telegram Message Format (exact)

```
SIGNAL
Coin:
BTCUSDT
Direction:
LONG ⬆️
Score:
12/14
Reason:
⬆️ EMA trend: BUY
⬆️ Supertrend: BUY
…
Action:
➡️ MUA LONG
Entry:
xxxx - xxxx
Stop Loss:
xxxx
Take Profit:
xxxx
```

## Development Roadmap

| Phase | Status | Content |
|-------|--------|---------|
| 1     | ✅     | Binance connection + Telegram + market data |
| 2     | ✅     | Indicators + scoring + signal generation |
| 3     | ✅     | Database + basic reports |
| 4a    | ✅     | Multi-symbol backtest engine + CLI report |
| 4b    | 🔜     | Persist runs to DB |
| 4c    | 🔜     | Streamlit dashboard |
| 5     | 🔒     | Auto-trading (only if you explicitly ask) |

## Important Rules

- Never auto-trade unless you request it.
- Always use closed candles.
- Same-coin cooldown = 30 min.
- Leverage reference = 10× (you choose size yourself).

## License

Private / personal use.
