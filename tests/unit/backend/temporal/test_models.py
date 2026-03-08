"""Tests for Temporal data models — serialization correctness.

Pure dataclass tests — no mocks, no infrastructure.
"""

import dataclasses

from modules.backend.temporal.models import (
    ApprovalDecision,
    MissionExecutionResult,
    MissionModification,
    MissionWorkflowInput,
    NotificationPayload,
    WorkflowStatus,
)


class TestMissionWorkflowInput:
    def test_required_fields(self):
        inp = MissionWorkflowInput(
            mission_id="abc",
            session_id="def",
            mission_brief="Do stuff",
        )
        assert inp.mission_id == "abc"
        assert inp.session_id == "def"
        assert inp.mission_brief == "Do stuff"

    def test_defaults(self):
        inp = MissionWorkflowInput(
            mission_id="abc", session_id="def", mission_brief="x",
        )
        assert inp.roster_name == "default"
        assert inp.mission_budget_usd == 10.0

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(MissionWorkflowInput)


class TestMissionExecutionResult:
    def test_defaults(self):
        result = MissionExecutionResult(mission_id="abc", status="success")
        assert result.total_cost_usd == 0.0
        assert result.task_count == 0
        assert result.outcome_json == {}

    def test_full_fields(self):
        result = MissionExecutionResult(
            mission_id="abc",
            status="partial",
            total_cost_usd=1.5,
            task_count=3,
            success_count=2,
            failed_count=1,
            outcome_json={"tasks": []},
        )
        assert result.failed_count == 1
        assert result.outcome_json == {"tasks": []}


class TestApprovalDecision:
    def test_approved(self):
        decision = ApprovalDecision(
            decision="approved",
            responder_type="human",
            responder_id="user_123",
            reason="Looks good",
        )
        assert decision.decision == "approved"
        assert decision.reason == "Looks good"

    def test_reason_optional(self):
        decision = ApprovalDecision(
            decision="rejected",
            responder_type="automated_rule",
            responder_id="rule:budget",
        )
        assert decision.reason is None


class TestWorkflowStatus:
    def test_defaults(self):
        status = WorkflowStatus(mission_id="abc")
        assert status.workflow_status == "pending"
        assert status.waiting_for_approval is False
        assert status.mission_status is None
        assert status.error is None


class TestNotificationPayload:
    def test_urgency_default(self):
        payload = NotificationPayload(
            channel="slack",
            recipient="admin",
            title="Test",
            body="Test body",
            action_url="/test",
        )
        assert payload.urgency == "normal"


class TestMissionModification:
    def test_defaults(self):
        mod = MissionModification()
        assert mod.instruction == ""
        assert mod.reasoning == ""
