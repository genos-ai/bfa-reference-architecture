"""
Project Context schemas.

Pydantic models for PCD operations, context updates, and API responses.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContextUpdateOp(BaseModel):
    """A single context update operation (JSON Patch-like)."""

    model_config = ConfigDict(extra="forbid")

    op: str = Field(
        ..., pattern=r"^(add|replace|remove)$",
        description="Operation type",
    )
    path: str = Field(
        ..., min_length=1, max_length=500,
        description="Dot-notation path in PCD (e.g. 'architecture.components.auth')",
    )
    value: Any = Field(
        None,
        description="Value to set (required for add/replace, ignored for remove)",
    )
    reason: str = Field(
        ..., min_length=1, max_length=500,
        description="Why this change is being made",
    )


class ContextUpdateRequest(BaseModel):
    """Batch of context update operations."""

    model_config = ConfigDict(extra="forbid")

    context_updates: list[ContextUpdateOp] = Field(
        ..., min_length=1,
        description="Ordered list of update operations to apply",
    )


class PCDResponse(BaseModel):
    """PCD content with metadata."""

    model_config = ConfigDict(from_attributes=True)

    project_id: str
    version: int
    size_characters: int
    size_tokens: int
    context_data: dict


class ContextChangeResponse(BaseModel):
    """Single context change audit entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    change_type: str
    path: str
    old_value: Any | None
    new_value: Any | None
    agent_id: str | None
    mission_id: str | None
    task_id: str | None
    reason: str
    created_at: str
