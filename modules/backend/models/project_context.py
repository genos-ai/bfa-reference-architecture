"""
Project Context Model.

The ProjectContext stores the Project Context Document (PCD) — a living,
curated JSON document that captures everything an agent needs to orient
itself within a project. The ContextChange table is the audit trail of
every PCD mutation.
"""

import enum

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class ChangeType(str, enum.Enum):
    """Type of PCD mutation."""

    ADD = "add"
    REPLACE = "replace"
    REMOVE = "remove"
    PRUNE = "prune"
    ARCHIVE = "archive"


class ProjectContext(UUIDMixin, TimestampMixin, Base):
    """The Project Context Document (PCD) for a single project.

    One row per project. Contains the entire PCD as a JSON blob.
    Versioned with monotonically increasing integer for optimistic concurrency.
    """

    __tablename__ = "project_contexts"

    project_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True,
    )
    context_data: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
    )
    size_characters: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    size_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectContext(project={self.project_id}, "
            f"version={self.version}, size={self.size_characters})>"
        )


class ContextChange(UUIDMixin, TimestampMixin, Base):
    """Audit trail entry for a single PCD mutation."""

    __tablename__ = "context_changes"

    context_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    change_type: Mapped[str] = mapped_column(
        Enum(ChangeType, native_enum=False), nullable=False,
    )
    path: Mapped[str] = mapped_column(
        String(500), nullable=False,
    )
    old_value: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    new_value: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )
    mission_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    execution_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
    )
    reason: Mapped[str] = mapped_column(
        Text, nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ContextChange(version={self.version}, "
            f"type={self.change_type}, path={self.path!r})>"
        )
