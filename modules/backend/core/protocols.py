"""Cross-boundary protocol definitions.

Protocols that decouple the services layer from the agents layer.
Both layers import from core — neither imports from the other.

SessionServiceProtocol: agents layer depends on this instead of
    the concrete SessionService.
MissionDispatchProtocol: services layer depends on this instead of
    the concrete MissionControlDispatchAdapter.
"""

from typing import Any, Protocol


class SessionServiceProtocol(Protocol):
    """Interface for session operations used by mission control.

    The agents layer codes against this protocol. The concrete
    SessionService in the services layer satisfies it structurally
    (no explicit registration needed).
    """

    async def get_session(self, session_id: str) -> Any: ...

    async def enforce_budget(
        self, session_id: str, estimated_cost: float = ...,
    ) -> None: ...

    async def get_messages(
        self, session_id: str, limit: int = ..., offset: int = ...,
    ) -> tuple[list, int]: ...

    async def update_cost(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None: ...

    async def touch_activity(self, session_id: str) -> None: ...

    async def add_message(self, session_id: str, data: Any) -> None: ...


class MissionDispatchProtocol(Protocol):
    """Interface for mission dispatch used by MissionService.

    The services layer codes against this protocol. The concrete
    MissionControlDispatchAdapter in the agents layer satisfies it
    structurally.
    """

    async def execute(
        self,
        mission_brief: str,
        roster_ref: str = ...,
        complexity_tier: str = ...,
        upstream_context: dict | None = ...,
        cost_ceiling_usd: float | None = ...,
        session_id: str | None = ...,
        project_id: str | None = ...,
    ) -> dict: ...
