"""PyQuality Index (PQI) — composite 0-100 code quality metric.

Public API:
    score_project()  — full pipeline orchestrator
"""

from modules.backend.services.pqi.scorer import score_project

__all__ = ["score_project"]
