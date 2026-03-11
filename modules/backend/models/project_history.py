"""
Project History Models.

Archived decisions and milestone summaries for Layer 2 history queries.
Decisions are pruned from the PCD after a configurable age threshold
and stored here for structured querying. Milestone summaries compress
completed mission batches into concise records.
"""

import enum

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class DecisionStatus(str, enum.Enum):
    """Decision lifecycle status."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVERSED = "reversed"


class ProjectDecision(UUIDMixin, TimestampMixin, Base):
    """Archived decision from PCD pruning, queryable by domain.

    When the PCD decisions section grows too large, older decisions are
    moved here. They remain queryable by domain and project for Layer 2
    context assembly.
    """

    __tablename__ = "project_decisions"

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_id: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    domain: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
    )
    decision: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    rationale: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    made_by: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )
    mission_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        Enum(DecisionStatus, native_enum=False),
        default=DecisionStatus.ACTIVE,
        nullable=False,
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectDecision(id={self.decision_id}, "
            f"domain={self.domain!r}, status={self.status})>"
        )


class MilestoneSummary(UUIDMixin, TimestampMixin, Base):
    """Compressed summary of a completed project phase.

    Created by the summarization pipeline when milestones are pruned
    from the PCD current_state section. Groups related missions and
    captures key outcomes for future context assembly.
    """

    __tablename__ = "milestone_summaries"

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(300), nullable=False,
    )
    summary: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    mission_ids: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
    )
    key_outcomes: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )
    domain_tags: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
    )
    period_start: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
    )
    period_end: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<MilestoneSummary(title={self.title!r}, "
            f"missions={len(self.mission_ids)})>"
        )
