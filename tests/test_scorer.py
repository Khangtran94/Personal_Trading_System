from signal_bot.indicators.signals import IndicatorSnapshot, SignalResult
from signal_bot.strategy.scorer import Scorer


def test_score_long():
    results = {
        "EMA": SignalResult("EMA", "BUY", weight=3),
        "Supertrend": SignalResult("Supertrend", "BUY", weight=3),
        "MACD_DIF": SignalResult("MACD_DIF", "BUY", weight=2),
        "Volume": SignalResult("Volume", "BUY", weight=2),
        "RSI": SignalResult("RSI", "BUY", weight=1),
        "KDJ": SignalResult("KDJ", "NEUTRAL", weight=0),
        "StochRSI": SignalResult("StochRSI", "NEUTRAL", weight=0),
        "Williams_R": SignalResult("Williams_R", "NEUTRAL", weight=0),
    }
    snap = IndicatorSnapshot(results=results, rsi=55.0)
    scorer = Scorer()
    total, _ = scorer.score(snap)
    assert total == 11
    assert scorer.decide(total) == "LONG"
    assert not scorer.apply_protection("LONG", snap)


def test_rsi_protection():
    snap = IndicatorSnapshot(results={}, rsi=85.0)
    scorer = Scorer()
    assert scorer.apply_protection("LONG", snap) is True
    assert scorer.apply_protection("SHORT", snap) is False
