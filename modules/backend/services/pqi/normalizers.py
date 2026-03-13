"""Normalization functions for PQI sub-metrics.

Each function maps a raw metric value to a 0-100 score using the
appropriate transformation:
    - sigmoid: for unbounded metrics (complexity, violation counts)
    - exp_decay: for count-based metrics (violations per KLOC)
    - linear: for bounded metrics (coverage percentages)
    - inverse_linear: for metrics where lower is better
"""

from __future__ import annotations

import math


def sigmoid(x: float, midpoint: float, k: float = 0.5) -> float:
    """Normalize unbounded metric to 0-100 via sigmoid.

    Score is 100 when x=0, ~50 at midpoint, ~0 for large x.

    Args:
        x: Raw metric value (higher = worse).
        midpoint: Value where score equals ~50.
        k: Steepness of the curve.
    """
    return 100.0 / (1.0 + math.exp(k * (x - midpoint)))


def exp_decay(count: float, rate: float = 0.5) -> float:
    """Normalize count-based metric via exponential decay.

    Score is 100 when count=0, decays toward 0 as count increases.

    Args:
        count: Raw count (e.g., violations per KLOC).
        rate: Decay rate (higher = faster penalty).
    """
    return 100.0 * math.exp(-rate * count)


def linear(value: float, max_value: float = 100.0) -> float:
    """Linear scaling for bounded 0-to-max metrics.

    Direct percentage mapping.
    """
    return max(0.0, min(100.0, (value / max_value) * 100.0)) if max_value > 0 else 0.0


def inverse_linear(value: float, good: float, bad: float) -> float:
    """Linear scaling where lower values are better.

    Score is 100 at ``good``, 0 at ``bad``.

    Args:
        value: Raw metric value.
        good: Value that scores 100.
        bad: Value that scores 0.
    """
    if bad == good:
        return 100.0 if value <= good else 0.0
    score = 100.0 * (bad - value) / (bad - good)
    return max(0.0, min(100.0, score))


def ratio_score(numerator: float, denominator: float) -> float:
    """Score a ratio as a percentage (0-100)."""
    if denominator <= 0:
        return 100.0
    return max(0.0, min(100.0, (numerator / denominator) * 100.0))
