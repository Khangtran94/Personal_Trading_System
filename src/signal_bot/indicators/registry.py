from __future__ import annotations

import pandas as pd
import pandas_ta as ta
from loguru import logger

from signal_bot.exchange.models import Candle, SignalSide
from signal_bot.indicators.signals import IndicatorSnapshot, SignalResult


WEIGHTS = {
    "EMA": 3,
    "Supertrend": 3,
    "MACD_DIF": 2,
    "Volume": 2,
    "RSI": 1,
    "KDJ": 1,
    "StochRSI": 1,
    "Williams_R": 1,
}


def candles_to_df(candles: list[Candle]) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "open_time": c.open_time,
            }
            for c in candles
        ]
    )
    df.set_index("open_time", inplace=True)
    return df


class IndicatorRegistry:
    """Compute the exact 8 indicators + ATR. All on closed candles only."""

    def compute(self, candles: list[Candle]) -> IndicatorSnapshot:
        if len(candles) < 60:
            logger.warning("Not enough candles for reliable indicators")
            return IndicatorSnapshot(results={})

        df = candles_to_df(candles)
        results: dict[str, SignalResult] = {}

        # --- EMA (20 / 50) ---
        ema20 = ta.ema(df["close"], length=20)
        ema50 = ta.ema(df["close"], length=50)
        df["ema20"] = ema20
        df["ema50"] = ema50
        last_close = float(df["close"].iloc[-1])
        last_ema20 = float(ema20.iloc[-1])
        last_ema50 = float(ema50.iloc[-1])
        prev_ema20 = float(ema20.iloc[-2])

        if last_close > last_ema20 and last_ema20 > last_ema50 and last_ema20 >= prev_ema20:
            side: SignalSide = "BUY"
            reason = "BUY"
        elif last_close < last_ema20 and last_ema20 < last_ema50 and last_ema20 <= prev_ema20:
            side = "SELL"
            reason = "SELL"
        else:
            side = "NEUTRAL"
            reason = "Neutral"
        results["EMA"] = SignalResult(
            name="EMA",
            side=side,
            value=last_ema20,
            weight=WEIGHTS["EMA"] if side == "BUY" else (-WEIGHTS["EMA"] if side == "SELL" else 0),
            reason=f"EMA trend: {reason}",
        )

        # --- Supertrend ---
        st = ta.supertrend(df["high"], df["low"], df["close"], length=10, multiplier=3.0)
        if st is not None and not st.empty:
            direction_col = [c for c in st.columns if "SUPERTd" in c][0]
            value_col = [c for c in st.columns if "SUPERT" in c and "SUPERTd" not in c][0]
            last_dir = int(st[direction_col].iloc[-1])
            if last_dir == 1:
                side = "BUY"
                reason = "BUY"
            elif last_dir == -1:
                side = "SELL"
                reason = "SELL"
            else:
                side = "NEUTRAL"
                reason = "Neutral"
            results["Supertrend"] = SignalResult(
                name="Supertrend",
                side=side,
                value=float(st[value_col].iloc[-1]),
                weight=WEIGHTS["Supertrend"] if side == "BUY" else (-WEIGHTS["Supertrend"] if side == "SELL" else 0),
                reason=f"Supertrend: {reason}",
            )
        else:
            results["Supertrend"] = SignalResult("Supertrend", "NEUTRAL", reason="Neutral")

        # --- MACD DIF ---
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            dif = macd.iloc[:, 0]  # MACD line
            dea = macd.iloc[:, 1]  # signal
            last_dif = float(dif.iloc[-1])
            prev_dif = float(dif.iloc[-2])
            if last_dif > 0 and last_dif > prev_dif:
                side = "BUY"
                reason = "BUY"
            elif last_dif < 0 and last_dif < prev_dif:
                side = "SELL"
                reason = "SELL"
            else:
                side = "NEUTRAL"
                reason = "Neutral"
            results["MACD_DIF"] = SignalResult(
                name="MACD_DIF",
                side=side,
                value=last_dif,
                weight=WEIGHTS["MACD_DIF"] if side == "BUY" else (-WEIGHTS["MACD_DIF"] if side == "SELL" else 0),
                reason=f"MACD DIF: {reason}",
            )
        else:
            results["MACD_DIF"] = SignalResult("MACD_DIF", "NEUTRAL", reason="Neutral")

        # --- Volume ---
        vol_sma = ta.sma(df["volume"], length=20)
        last_vol = float(df["volume"].iloc[-1])
        last_vol_sma = float(vol_sma.iloc[-1])
        price_up = last_close > float(df["close"].iloc[-2])
        if last_vol > last_vol_sma and price_up:
            side = "BUY"
            reason = "Increasing"
        elif last_vol > last_vol_sma and not price_up:
            side = "SELL"
            reason = "Increasing"
        else:
            side = "NEUTRAL"
            reason = "Neutral"
        results["Volume"] = SignalResult(
            name="Volume",
            side=side,
            value=last_vol,
            weight=WEIGHTS["Volume"] if side == "BUY" else (-WEIGHTS["Volume"] if side == "SELL" else 0),
            reason=f"Volume: {reason}",
        )

        # --- RSI ---
        rsi = ta.rsi(df["close"], length=14)
        last_rsi = float(rsi.iloc[-1])
        prev_rsi = float(rsi.iloc[-2])
        if 40 <= last_rsi <= 70 and last_rsi > prev_rsi:
            side = "BUY"
            reason = f"{last_rsi:.0f}"
        elif 30 <= last_rsi <= 60 and last_rsi < prev_rsi:
            side = "SELL"
            reason = f"{last_rsi:.0f}"
        else:
            side = "NEUTRAL"
            reason = f"{last_rsi:.0f}"
        results["RSI"] = SignalResult(
            name="RSI",
            side=side,
            value=last_rsi,
            weight=WEIGHTS["RSI"] if side == "BUY" else (-WEIGHTS["RSI"] if side == "SELL" else 0),
            reason=f"RSI: {reason}",
        )

        # --- KDJ ---
        stoch = ta.stoch(df["high"], df["low"], df["close"], k=9, d=3, smooth_k=3)
        if stoch is not None and not stoch.empty:
            k = stoch.iloc[:, 0]
            d = stoch.iloc[:, 1]
            last_k, last_d = float(k.iloc[-1]), float(d.iloc[-1])
            prev_k, prev_d = float(k.iloc[-2]), float(d.iloc[-2])
            if last_k > last_d and last_k > prev_k and last_d > prev_d and last_k < 80:
                side = "BUY"
                reason = "BUY"
            elif last_k < last_d and last_k < prev_k and last_d < prev_d and last_k > 20:
                side = "SELL"
                reason = "SELL"
            else:
                side = "NEUTRAL"
                reason = "Neutral"
            results["KDJ"] = SignalResult(
                name="KDJ",
                side=side,
                value=last_k,
                weight=WEIGHTS["KDJ"] if side == "BUY" else (-WEIGHTS["KDJ"] if side == "SELL" else 0),
                reason=f"KDJ: {reason}",
            )
        else:
            results["KDJ"] = SignalResult("KDJ", "NEUTRAL", reason="Neutral")

        # --- StochRSI ---
        stochrsi = ta.stochrsi(df["close"], length=14, rsi_length=14, k=3, d=3)
        if stochrsi is not None and not stochrsi.empty:
            k_col = stochrsi.iloc[:, 0]
            last_srsi = float(k_col.iloc[-1])
            prev_srsi = float(k_col.iloc[-2])
            if last_srsi > prev_srsi and prev_srsi < 20:
                side = "BUY"
                reason = "BUY"
            elif last_srsi < prev_srsi and prev_srsi > 80:
                side = "SELL"
                reason = "SELL"
            else:
                side = "NEUTRAL"
                reason = "Neutral"
            results["StochRSI"] = SignalResult(
                name="StochRSI",
                side=side,
                value=last_srsi,
                weight=WEIGHTS["StochRSI"] if side == "BUY" else (-WEIGHTS["StochRSI"] if side == "SELL" else 0),
                reason=f"StochRSI: {reason}",
            )
        else:
            results["StochRSI"] = SignalResult("StochRSI", "NEUTRAL", reason="Neutral")

        # --- Williams %R ---
        willr = ta.willr(df["high"], df["low"], df["close"], length=14)
        last_wr = float(willr.iloc[-1])
        prev_wr = float(willr.iloc[-2])
        if last_wr > -80 and prev_wr <= -80:
            side = "BUY"
            reason = "BUY"
        elif last_wr < -20 and prev_wr >= -20:
            side = "SELL"
            reason = "SELL"
        else:
            side = "NEUTRAL"
            reason = "Neutral"
        results["Williams_R"] = SignalResult(
            name="Williams_R",
            side=side,
            value=last_wr,
            weight=WEIGHTS["Williams_R"] if side == "BUY" else (-WEIGHTS["Williams_R"] if side == "SELL" else 0),
            reason=f"Williams %R: {reason}",
        )

        # ATR
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        last_atr = float(atr.iloc[-1]) if atr is not None else None

        return IndicatorSnapshot(
            results=results,
            atr=last_atr,
            ema20=last_ema20,
            close=last_close,
            rsi=last_rsi,
        )
