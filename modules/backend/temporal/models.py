"""
Temporal workflow data models.

Serializable dataclasses for workflow inputs, outputs, and signals.
No ORM objects — Temporal serializes these as JSON. Activities convert
between these DTOs and domain objects.
"""

from dataclasses import dataclass, field


@dataclass
class MissionWorkflowInput:
    """Input to start an AgentMissionWorkflow."""

    mission_id: str
    session_id: str
    mission_brief: str
    roster_name: str = "default"
    mission_budget_usd: float = 10.0
    approval_timeout_seconds: int = 14400
    escalation_timeout_seconds: int = 86400
    notification_timeout_seconds: int = 30


@dataclass
class MissionExecutionResult:
    """Output from the execute_mission Activity.

    Carries the serialized MissionOutcome from dispatch.
    """

    mission_id: str
    status: str  # "success", "partial", "failed"
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    task_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    outcome_json: dict = field(default_factory=dict)


@dataclass
class ApprovalDecision:
    """Input from a Signal: human/AI/rule approval decision."""

    decision: str  # "approved", "rejected", "modified"
    responder_type: str  # "human", "ai_agent", "automated_rule"
    responder_id: str
    reason: str | None = None


@dataclass
class MissionModification:
    """Input from a Signal: mission modification mid-execution."""

    instruction: str = ""
    reasoning: str = ""


@dataclass
class WorkflowStatus:
    """Output from a Query: current workflow state."""

    mission_id: str
    workflow_status: str = "pending"
    mission_status: str | None = None
    total_cost_usd: float = 0.0
    waiting_for_approval: bool = False
    error: str | None = None


@dataclass
class NotificationPayload:
    """Input for the send_notification Activity."""

    channel: str  # "slack", "email", "webhook"
    recipient: str
    title: str
    body: str
    action_url: str
    urgency: str = "normal"  # "low", "normal", "high", "critical"
