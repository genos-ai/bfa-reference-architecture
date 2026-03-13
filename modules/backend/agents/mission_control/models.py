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

from modules.backend.core.protocols import MissionDispatchProtocol, SessionServiceProtocol
from modules.backend.events.types import SessionEvent

# Re-export protocols so existing imports from models.py continue to work
__all__ = [
    "MissionControlRequest",
    "MissionControlResponse",
    "EventBusProtocol",
    "ExecuteAgentFn",
    "NoOpEventBus",
    "SessionServiceProtocol",
    "MissionDispatchProtocol",
    "ContextCuratorProtocol",
    "ContextAssemblerProtocol",
    "CollectResult",
]


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


class NoOpEventBus:
    """Null-object event bus — satisfies EventBusProtocol, does nothing.

    Use as the default instead of None to eliminate None-checks at
    every publish call site.
    """

    async def publish(self, event: SessionEvent) -> None:
        pass


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


class ContextCuratorProtocol(Protocol):
    """Interface for context curator used by dispatch.

    Keeps the dispatch loop decoupled from PCD service internals.
    """

    async def get_project_context(self, project_id: str) -> dict: ...

    async def apply_task_updates(
        self,
        project_id: str,
        task_result_context_updates: list[dict],
        *,
        agent_id: str | None = ...,
        mission_id: str | None = ...,
        task_id: str | None = ...,
    ) -> tuple[int, list[str]]: ...


class ContextAssemblerProtocol(Protocol):
    """Interface for context assembler used by dispatch.

    Builds full context packets (PCD + history + Code Map) for agent tasks.
    """

    async def build(
        self,
        project_id: str,
        task_definition: dict,
        resolved_inputs: dict,
        *,
        domain_tags: list[str] | None = ...,
        token_budget: int = ...,
        code_map_max_tokens: int | None = ...,
    ) -> dict: ...


class CollectResult(TypedDict):
    """Return type of mission_control.collect()."""

    agent_name: str
    output: str
    cost_usd: float
    session_id: str
    thinking: str | None
