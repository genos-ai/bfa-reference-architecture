"""
Coordinator request and response models.

Typed models for all coordinator interactions. Every entry point
(API, CLI, Telegram, TUI) constructs a CoordinatorRequest and
receives a CoordinatorResponse.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CoordinatorRequest:
    """Typed request for all coordinator interactions."""

    user_input: str
    agent: str | None = None
    conversation_id: str | None = None
    channel: str = "api"
    session_type: str = "direct"
    tool_access_level: str = "sandbox"


@dataclass
class CoordinatorResponse:
    """Typed response from the coordinator."""

    agent_name: str
    output: str
    metadata: dict[str, Any] = field(default_factory=dict)
