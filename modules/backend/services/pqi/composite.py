"""Penalized weighted geometric mean — the PQI composite formula.

The geometric mean reduces compensability compared to arithmetic mean:
a project with 95 in six dimensions but 5 in security cannot score
above ~60. The floor penalty mechanism ensures critical gaps are
impossible to hide behind high scores elsewhere.
"""

from __future__ import annotations

import math

from modules.backend.services.pqi.types import (
    WEIGHT_PROFILES,
    DimensionScore,
    PQIResult,
    classify_band,
)

CRITICAL_FLOOR = 20


def compute_pqi(
    dimensions: dict[str, DimensionScore],
    profile: str = "production",
    file_count: int = 0,
    line_count: int = 0,
) -> PQIResult:
    """Compute the composite PQI score from dimension scores.

    Formula: PQI = min(100, floor_penalty × ∏(Dᵢ^wᵢ))

    Args:
        dimensions: Mapping of dimension name → DimensionScore.
        profile: Weight profile name (production, library, etc.).
        file_count: Total source files analyzed.
        line_count: Total source lines analyzed.

    Returns:
        PQIResult with composite score, band, and penalty info.
    """
    weights = WEIGHT_PROFILES.get(profile, WEIGHT_PROFILES["production"])

    # Clamp scores to [1, 100] to avoid zero-product collapse
    scores = {k: max(1.0, v.score) for k, v in dimensions.items()}

    # Compute penalized weighted geometric mean
    log_sum = 0.0
    for dim_name, weight in weights.items():
        score = scores.get(dim_name, 50.0)  # Default 50 for missing dimensions
        log_sum += weight * math.log(score)

    geometric_mean = math.exp(log_sum)

    # Apply floor penalty
    penalty = floor_penalty(scores)
    composite = min(100.0, geometric_mean * penalty)

    return PQIResult(
        composite=round(composite, 1),
        dimensions=dimensions,
        quality_band=classify_band(composite),
        floor_penalty=round(penalty, 3),
        file_count=file_count,
        line_count=line_count,
    )


def floor_penalty(dimension_scores: dict[str, float]) -> float:
    """Compute floor penalty for dimensions below critical threshold.

    Any dimension below CRITICAL_FLOOR (20) triggers a penalty.
    Each violation reduces the composite by up to 30%.
    The penalty itself floors at 0.3 (never completely zeros out).
    """
    violations = [s for s in dimension_scores.values() if s < CRITICAL_FLOOR]
    if not violations:
        return 1.0

    penalty = 1.0
    for score in violations:
        deficit = (CRITICAL_FLOOR - score) / CRITICAL_FLOOR
        penalty *= (1.0 - 0.3 * deficit)

    return max(0.3, penalty)
