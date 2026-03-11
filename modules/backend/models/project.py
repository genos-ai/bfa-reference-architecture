"""
Project Model.

A Project is the top-level organizational boundary. It groups all missions,
playbook runs, context, and history for a single codebase or initiative.
Projects are long-lived (months to years), owned by humans, and scoped —
agents operate within a single project at a time.
"""

import enum

from sqlalchemy import Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class ProjectStatus(str, enum.Enum):
    """Project lifecycle status."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ProjectMemberRole(str, enum.Enum):
    """Project membership role."""

    OWNER = "owner"
    MAINTAINER = "maintainer"
    VIEWER = "viewer"


class Project(UUIDMixin, TimestampMixin, Base):
    """A long-lived project that groups missions, context, and history."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True,
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Enum(ProjectStatus, native_enum=False),
        default=ProjectStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    owner_id: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True,
    )
    team_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )
    default_roster: Mapped[str] = mapped_column(
        String(100), default="default", nullable=False,
    )
    budget_ceiling_usd: Mapped[float | None] = mapped_column(
        Float, nullable=True,
    )
    repo_url: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    repo_root: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Project(id={self.id}, name={self.name!r}, "
            f"status={self.status})>"
        )


class ProjectMember(UUIDMixin, TimestampMixin, Base):
    """Human membership in a project with role-based permissions."""

    __tablename__ = "project_members"

    project_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(
        Enum(ProjectMemberRole, native_enum=False),
        default=ProjectMemberRole.VIEWER,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectMember(project={self.project_id}, "
            f"user={self.user_id}, role={self.role})>"
        )
