"""
Escalation Chain.

Deterministic escalation path when approval goes unanswered
or a task exceeds an agent's capability.

P2 PRINCIPLE: Deterministic over Non-Deterministic.
All escalation logic is rule-based. No LLM calls.

Levels:
1. Low-risk rules (immediate) — read-only, low cost
2. Risk matrix (immediate) — configurable thresholds
3. Human (4h timeout) — Slack/email notification
4. Manager (24h timeout) — escalation after Level 3 timeout
"""

from dataclasses import dataclass, field

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EscalationLevel:
    """A single level in the escalation chain."""

    level: int
    responder_type: str
    timeout_seconds: int
    description: str


ESCALATION_CHAIN = [
    EscalationLevel(
        level=1,
        responder_type="automated_rule_low_risk",
        timeout_seconds=0,
        description="Deterministic rules for low-risk actions",
    ),
    EscalationLevel(
        level=2,
        responder_type="automated_rule_medium_risk",
        timeout_seconds=0,
        description="Risk matrix for medium-complexity actions",
    ),
    EscalationLevel(
        level=3,
        responder_type="human",
        timeout_seconds=14400,
        description="Human review via Slack/email",
    ),
    EscalationLevel(
        level=4,
        responder_type="human_manager",
        timeout_seconds=86400,
        description="Manager escalation",
    ),
]


def get_escalation_level(current_level: int) -> EscalationLevel | None:
    """Get the escalation level by number."""
    for level in ESCALATION_CHAIN:
        if level.level == current_level:
            return level
    return None


def get_next_escalation(current_level: int) -> EscalationLevel | None:
    """Get the next escalation level. None if at highest."""
    for level in ESCALATION_CHAIN:
        if level.level == current_level + 1:
            return level
    return None


# ---- Risk classification (P2: all deterministic) ----

LOW_RISK_ACTIONS = frozenset({
    "read_file", "list_files", "get_status", "get_mission_status",
    "list_available_agents",
})

MEDIUM_RISK_ACTIONS = frozenset({
    "invoke_agent", "apply_fix", "run_tests", "create_mission",
    "revise_mission",
})


@dataclass
class RiskThresholds:
    """Configurable thresholds for deterministic risk classification."""

    max_auto_approve_cost_usd: float = 1.00
    max_medium_approve_cost_usd: float = 10.00
    max_auto_approve_retries: int = 3
    allowed_retry_actions: frozenset[str] = field(
        default_factory=lambda: frozenset({
            "invoke_agent", "apply_fix", "run_tests",
        }),
    )


_thresholds = RiskThresholds()


async def evaluate_automated_rules(
    action: str,
    context: dict,
) -> dict | None:
    """Level 1: Check if action can be auto-approved by low-risk rules.

    Returns approval decision if rules match, None to escalate.
    """
    if action in LOW_RISK_ACTIONS:
        return {
            "decision": "approved",
            "responder_type": "automated_rule",
            "responder_id": "rule:low_risk_action",
            "reason": f"Auto-approved: '{action}' is a low-risk action",
        }

    cost = context.get("estimated_cost_usd", 0)
    if cost < _thresholds.max_auto_approve_cost_usd:
        return {
            "decision": "approved",
            "responder_type": "automated_rule",
            "responder_id": "rule:low_cost",
            "reason": (
                f"Auto-approved: estimated cost ${cost:.2f} "
                f"< ${_thresholds.max_auto_approve_cost_usd:.2f}"
            ),
        }

    if (
        context.get("is_retry")
        and action in _thresholds.allowed_retry_actions
        and context.get("retry_count", 0) <= _thresholds.max_auto_approve_retries
    ):
        return {
            "decision": "approved",
            "responder_type": "automated_rule",
            "responder_id": "rule:retry_auto_approve",
            "reason": (
                f"Auto-approved: retry {context['retry_count']} "
                f"of previously approved '{action}'"
            ),
        }

    return None


async def evaluate_risk_matrix(
    action: str,
    context: dict,
) -> dict | None:
    """Level 2: Risk matrix for medium-complexity decisions.

    Deterministic classification based on action type, cost, agent
    permissions, and error category.
    """
    cost = context.get("estimated_cost_usd", 0)

    if (
        action in MEDIUM_RISK_ACTIONS
        and cost < _thresholds.max_medium_approve_cost_usd
    ):
        agent = context.get("agent_name", "")
        allowed = context.get("allowed_agents", set())
        if agent in allowed or not agent:
            return {
                "decision": "approved",
                "responder_type": "automated_rule",
                "responder_id": "rule:risk_matrix_medium",
                "reason": (
                    f"Risk matrix approved: '{action}' with cost "
                    f"${cost:.2f} within medium threshold"
                ),
            }

    error_category = context.get("error_category")
    safe_error_categories = {"timeout", "rate_limit", "transient_network"}
    if error_category in safe_error_categories:
        return {
            "decision": "approved",
            "responder_type": "automated_rule",
            "responder_id": "rule:safe_error_category",
            "reason": (
                f"Risk matrix approved: error category "
                f"'{error_category}' is transient/recoverable"
            ),
        }

    return None
