from signal_bot.indicators.signals import IndicatorSnapshot, SignalResult
from signal_bot.strategy.scorer import Scorer


def _snap_all_buy_volume() -> IndicatorSnapshot:
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
    return IndicatorSnapshot(results=results, rsi=55.0)


def test_score_long_default():
    snap = _snap_all_buy_volume()
    scorer = Scorer(profile="default", buy_threshold=10, sell_threshold=-10)
    total, _ = scorer.score(snap)
    assert total == 11  # 3+3+2+2+1
    assert scorer.decide(total) == "LONG"
    assert not scorer.apply_protection("LONG", snap)


def test_score_long_no_volume():
    snap = _snap_all_buy_volume()
    scorer = Scorer(profile="no_volume", buy_threshold=10, sell_threshold=-10)
    total, ordered = scorer.score(snap)
    assert total == 9  # volume weight 0 → 3+3+2+0+1
    vol = next(r for r in ordered if r.name == "Volume")
    assert vol.weight == 0
    assert scorer.decide(total) is None  # 9 < 10


def test_rsi_protection():
    snap = IndicatorSnapshot(results={}, rsi=85.0)
    scorer = Scorer()
    assert scorer.apply_protection("LONG", snap) is True
    assert scorer.apply_protection("SHORT", snap) is False
