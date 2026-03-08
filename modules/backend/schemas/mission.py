"""
Mission API schemas.

Request/response models for mission CRUD, status reporting,
and playbook-to-mission conversion.
"""

from pydantic import BaseModel, ConfigDict, Field


class MissionCreate(BaseModel):
    """Create an ad-hoc mission (not from a playbook)."""

    objective: str = Field(..., description="Mission objective")
    roster_ref: str = Field(default="default")
    complexity_tier: str = Field(default="simple")
    triggered_by: str = Field(default="user:anonymous")
    cost_ceiling_usd: float | None = None
    upstream_context: dict | None = None


class MissionResponse(BaseModel):
    """API response for a mission."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    playbook_run_id: str | None
    playbook_step_id: str | None
    objective: str
    roster_ref: str
    complexity_tier: str
    status: str
    session_id: str
    trigger_type: str
    triggered_by: str
    total_cost_usd: float
    cost_ceiling_usd: float | None
    started_at: str | None
    completed_at: str | None


class MissionDetailResponse(BaseModel):
    """Detailed mission response with context and results."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    playbook_run_id: str | None
    playbook_step_id: str | None
    objective: str
    roster_ref: str
    complexity_tier: str
    status: str
    session_id: str
    trigger_type: str
    triggered_by: str
    upstream_context: dict
    context: dict
    total_cost_usd: float
    cost_ceiling_usd: float | None
    started_at: str | None
    completed_at: str | None
    result_summary: str | None
    error_data: dict | None


class MissionStateSummary(BaseModel):
    """Mission progress summary."""

    mission_id: str
    objective: str
    status: str
    roster_ref: str
    total_cost_usd: float
    cost_ceiling_usd: float | None
    started_at: str | None
    elapsed_seconds: float | None
