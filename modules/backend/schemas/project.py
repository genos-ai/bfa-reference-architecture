"""
Project API schemas.

Pydantic models for project creation, update, and response serialization.
"""

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ..., min_length=1, max_length=200,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Unique project name (lowercase, hyphens, underscores)",
    )
    description: str = Field(
        ..., min_length=1, max_length=2000,
        description="Project purpose and scope",
    )
    owner_id: str = Field(
        ..., min_length=1, max_length=200,
        description="Primary human owner identifier",
    )
    team_id: str | None = Field(
        None, max_length=200,
        description="Optional team identifier",
    )
    default_roster: str = Field(
        default="default",
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Default agent roster for this project",
    )
    budget_ceiling_usd: float | None = Field(
        None, ge=0.01,
        description="Project-level spend cap",
    )
    repo_url: str | None = Field(
        None, max_length=2000,
        description="Source repository URL",
    )
    repo_root: str | None = Field(
        None, max_length=1000,
        description="Local filesystem root path",
    )


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(None, min_length=1, max_length=2000)
    status: str | None = Field(None, pattern=r"^(active|paused|archived)$")
    default_roster: str | None = Field(None, pattern=r"^[a-z][a-z0-9_-]*$")
    budget_ceiling_usd: float | None = None
    repo_url: str | None = None
    repo_root: str | None = None


class ProjectResponse(BaseModel):
    """Schema for project API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    status: str
    owner_id: str
    team_id: str | None
    default_roster: str
    budget_ceiling_usd: float | None
    repo_url: str | None
    repo_root: str | None
    created_at: str
    updated_at: str


class ProjectMemberResponse(BaseModel):
    """Schema for project member API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    user_id: str
    role: str
    created_at: str
