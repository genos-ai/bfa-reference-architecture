"""
Mission Control request and response models.

Typed models for all mission control interactions. Every entry point
(API, CLI, Telegram, TUI) constructs a MissionControlRequest and
receives a MissionControlResponse.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MissionControlRequest:
    """Typed request for all mission control interactions."""

    user_input: str
    agent: str | None = None
    conversation_id: str | None = None

    # Reserved for doc 44 (multi-channel gateway) integration.
    # Set by the gateway after security/session resolution.
    # Not read by routing or execution until gateway is implemented.
    channel: str = "api"
    session_type: str = "direct"
    tool_access_level: str = "sandbox"


@dataclass
class MissionControlResponse:
    """Standard response from mission control.

    Every public mission control function returns data in this shape.
    agent_name identifies who handled the request, output is the
    primary text result, and metadata carries agent-specific payload
    (violations, components, advice, etc.).
    """

    agent_name: str
    output: str
    metadata: dict[str, Any] = field(default_factory=dict)
