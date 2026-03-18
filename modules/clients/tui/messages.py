"""Custom Textual Message types for TUI inter-component communication.

These bridge backend events and user actions to Textual's message loop.
"""

from __future__ import annotations

from textual.message import Message

from modules.backend.agents.mission_control.gate import GateContext, GateDecision
from modules.backend.events.types import SessionEvent


class SessionEventReceived(Message):
    """A backend SessionEvent arrived via the event bus."""

    def __init__(self, event: SessionEvent) -> None:
        super().__init__()
        self.event = event


class GateReviewRequested(Message):
    """Dispatch is waiting for a human gate decision."""

    def __init__(self, context: GateContext) -> None:
        super().__init__()
        self.context = context


class GateReviewCompleted(Message):
    """User resolved a gate decision (from GateReviewModal)."""

    def __init__(self, decision: GateDecision) -> None:
        super().__init__()
        self.decision = decision


class AgentSelected(Message):
    """User clicked an agent in the sidebar."""

    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.agent_name = agent_name


class MissionStartRequested(Message):
    """User wants to start a new mission."""

    def __init__(self, brief: str) -> None:
        super().__init__()
        self.brief = brief


class MissionCancelRequested(Message):
    """User pressed Ctrl+K to cancel the active mission."""


class ProjectSelected(Message):
    """User picked a project in the project picker."""

    def __init__(self, project_id: str, project_name: str) -> None:
        super().__init__()
        self.project_id = project_id
        self.project_name = project_name


class ProjectCreated(Message):
    """User wants to create a new project (pre-persistence)."""

    def __init__(self, project_name: str, description: str = "") -> None:
        super().__init__()
        self.project_name = project_name
        self.description = description
