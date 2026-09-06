from __future__ import annotations

"""Scoring weight profiles (duplicate strategies for A/B backtests)."""

# Max |score| = sum of absolute weights
PROFILES: dict[str, dict[str, int]] = {
    # Original: volume is a core confirmer (weight 2). Max ±14
    "default": {
        "EMA": 3,
        "Supertrend": 3,
        "MACD_DIF": 2,
        "Volume": 2,
        "RSI": 1,
        "KDJ": 1,
        "StochRSI": 1,
        "Williams_R": 1,
    },
    # Volume not central: indicator still computed for display, weight 0. Max ±12
    "no_volume": {
        "EMA": 3,
        "Supertrend": 3,
        "MACD_DIF": 2,
        "Volume": 0,
        "RSI": 1,
        "KDJ": 1,
        "StochRSI": 1,
        "Williams_R": 1,
    },
}

DEFAULT_PROFILE = "default"


def get_weights(profile: str) -> dict[str, int]:
    key = (profile or DEFAULT_PROFILE).strip().lower()
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown score profile '{profile}'. Choose one of: {known}")
    return PROFILES[key]


def max_score(profile: str) -> int:
    return sum(get_weights(profile).values())
