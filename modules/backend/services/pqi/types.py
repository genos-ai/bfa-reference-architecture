"""Data types for the PyQuality Index (PQI) scoring system.

Defines the scoring result types, dimension weights, and quality bands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class QualityBand(str, Enum):
    """Quality rating bands based on composite PQI score."""

    POOR = "Poor"                # 0-30
    ACCEPTABLE = "Acceptable"    # 31-54
    ADEQUATE = "Adequate"        # 55-64
    GOOD = "Good"                # 65-79
    EXCELLENT = "Excellent"      # 80-100


@dataclass
class DimensionScore:
    """Score for a single quality dimension (0-100)."""

    name: str
    score: float
    sub_scores: dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PQIResult:
    """Complete PQI scoring result."""

    composite: float
    dimensions: dict[str, DimensionScore] = field(default_factory=dict)
    quality_band: QualityBand = QualityBand.POOR
    floor_penalty: float = 1.0
    file_count: int = 0
    line_count: int = 0


# Weight profiles from the research doc
WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "production": {
        "maintainability": 0.20,
        "security": 0.15,
        "modularity": 0.15,
        "testability": 0.15,
        "robustness": 0.13,
        "elegance": 0.12,
        "reusability": 0.10,
    },
    "library": {
        "maintainability": 0.15,
        "security": 0.10,
        "modularity": 0.20,
        "testability": 0.15,
        "robustness": 0.10,
        "elegance": 0.15,
        "reusability": 0.15,
    },
    "data_science": {
        "maintainability": 0.15,
        "security": 0.10,
        "modularity": 0.10,
        "testability": 0.20,
        "robustness": 0.15,
        "elegance": 0.15,
        "reusability": 0.15,
    },
    "safety_critical": {
        "maintainability": 0.15,
        "security": 0.25,
        "modularity": 0.10,
        "testability": 0.20,
        "robustness": 0.15,
        "elegance": 0.05,
        "reusability": 0.10,
    },
}


def classify_band(score: float) -> QualityBand:
    """Map a composite score to a quality band."""
    if score >= 80:
        return QualityBand.EXCELLENT
    if score >= 65:
        return QualityBand.GOOD
    if score >= 55:
        return QualityBand.ADEQUATE
    if score >= 31:
        return QualityBand.ACCEPTABLE
    return QualityBand.POOR
