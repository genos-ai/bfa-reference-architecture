"""
Approval Request Module.

Provides request_approval() for Tier 3 (Redis event bus).
In Tier 4, approval is handled by the workflow via Temporal Signals —
this function should not be called in Tier 4.
"""

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


async def request_approval(
    mission_id: str,
    task_id: str,
    action: str,
    context: dict,
    timeout_seconds: int = 14400,
) -> dict:
    """Request approval via event bus (Tier 3 only).

    In Tier 4, the workflow handles approval via Temporal Signals.
    """
    config = get_app_config()

    if config.temporal.enabled:
        raise RuntimeError(
            "request_approval() should not be called in Tier 4. "
            "The workflow handles approval via Temporal Signals."
        )

    logger.info(
        "Approval requested (Tier 3)",
        extra={
            "mission_id": mission_id,
            "task_id": task_id,
            "action": action,
        },
    )

    # Stub: auto-approve in dev mode
    # Future: publish ApprovalRequestedEvent to event bus,
    # wait for ApprovalResponseEvent
    return {
        "decision": "approved",
        "responder_type": "automated_rule",
        "responder_id": "auto_approve_dev_mode",
        "reason": "Auto-approved in dev mode (Tier 3 stub)",
    }
