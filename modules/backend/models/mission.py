"""
Mission Model.

A mission is a discrete objective with bounded scope. When created by a
Playbook, each mission has its own roster, complexity tier, and upstream
context. The Mission instantiates Mission Control with these parameters.

Missions created by Playbooks have a playbook_run_id linking them to
their parent PlaybookRun. Ad-hoc missions (from direct API calls) have
no playbook_run_id.
"""

import enum

from sqlalchemy import Enum, Float, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class MissionState(str, enum.Enum):
    """Mission lifecycle status.

    Transitions:
        pending -> running (execution started)
        running -> completed (all tasks done)
        running -> failed (unrecoverable error)
        running -> cancelled (user cancelled)
        pending -> cancelled (cancelled before start)
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


VALID_MISSION_TRANSITIONS: dict[MissionState, set[MissionState]] = {
    MissionState.PENDING: {MissionState.RUNNING, MissionState.CANCELLED},
    MissionState.RUNNING: {
        MissionState.COMPLETED,
        MissionState.FAILED,
        MissionState.CANCELLED,
    },
    MissionState.COMPLETED: set(),
    MissionState.FAILED: set(),
    MissionState.CANCELLED: set(),
}


class PlaybookRunState(str, enum.Enum):
    """Playbook run lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlaybookRun(UUIDMixin, TimestampMixin, Base):
    """A single execution of a playbook."""

    __tablename__ = "playbook_runs"

    playbook_name: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True,
    )
    playbook_version: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Enum(PlaybookRunState, native_enum=False),
        default=PlaybookRunState.PENDING,
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
    )
    trigger_type: Mapped[str] = mapped_column(
        String(50), default="on_demand", nullable=False,
    )
    triggered_by: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )
    context: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )
    total_cost_usd: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )
    budget_usd: Mapped[float | None] = mapped_column(
        Float, nullable=True,
    )
    started_at: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
    )
    completed_at: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
    )
    error_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    result_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<PlaybookRun(id={self.id}, playbook={self.playbook_name!r}, "
            f"status={self.status})>"
        )


class Mission(UUIDMixin, TimestampMixin, Base):
    """A runtime mission — a discrete objective with bounded scope."""

    __tablename__ = "missions"

    playbook_run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
    )
    playbook_step_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    objective: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    roster_ref: Mapped[str] = mapped_column(
        String(100), default="default", nullable=False,
    )
    complexity_tier: Mapped[str] = mapped_column(
        String(20), default="simple", nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Enum(MissionState, native_enum=False),
        default=MissionState.PENDING,
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
    )
    trigger_type: Mapped[str] = mapped_column(
        String(50), default="on_demand", nullable=False,
    )
    triggered_by: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )
    upstream_context: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )
    context: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )
    total_cost_usd: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )
    cost_ceiling_usd: Mapped[float | None] = mapped_column(
        Float, nullable=True,
    )
    started_at: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
    )
    completed_at: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
    )
    error_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    mission_outcome: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    result_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Mission(id={self.id}, objective={self.objective[:50]!r}, "
            f"status={self.status}, roster={self.roster_ref})>"
        )
