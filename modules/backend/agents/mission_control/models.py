"""
Mission Control request, response, and protocol models.

Typed models for all mission control interactions. Every entry point
(API, CLI, Telegram, TUI) constructs a MissionControlRequest and
receives a MissionControlResponse.

Protocol types define the interfaces used across mission control
to eliminate Any annotations while avoiding circular imports.
"""

from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict, runtime_checkable

from pydantic_ai import UsageLimits

from modules.backend.events.types import SessionEvent


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


# ---------------------------------------------------------------------------
# Protocol types — eliminate Any across mission control interfaces
# ---------------------------------------------------------------------------


@runtime_checkable
class EventBusProtocol(Protocol):
    """Interface for event bus implementations (SessionEventBus, mocks, etc.)."""

    async def publish(self, event: SessionEvent) -> None: ...


class ExecuteAgentFn(Protocol):
    """Callable protocol for agent execution used by dispatch and verification.

    Signature matches the closure returned by _make_agent_executor().
    """

    def __call__(
        self,
        agent_name: str,
        instructions: str,
        inputs: dict,
        usage_limits: UsageLimits,
    ) -> Awaitable[dict]: ...


class CollectResult(TypedDict):
    """Return type of mission_control.collect()."""

    agent_name: str
    output: str
    cost_usd: float
    session_id: str
    thinking: str | None
