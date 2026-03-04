"""Session service — lifecycle management for the platform primitive."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config import get_app_config
from modules.backend.core.exceptions import BudgetExceededError, NotFoundError, ValidationError
from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now
from modules.backend.models.session import Session, SessionChannel, SessionStatus, VALID_TRANSITIONS
from modules.backend.repositories.session import SessionRepository
from modules.backend.schemas.session import (
    SessionCreate,
    SessionMessageCreate,
    SessionUpdate,
)
from modules.backend.services.base import BaseService

logger = get_logger(__name__)


class SessionService(BaseService):
    """Manages session lifecycle. Does not contain agent logic — that lives in mission control."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repo = SessionRepository(session)

    # --- Lifecycle ---

    async def create_session(
        self,
        data: SessionCreate,
        user_id: str | None = None,
    ) -> Session:
        """Create a new session with TTL and cost budget from config defaults."""
        config = get_app_config().sessions

        # Resolve TTL
        ttl_hours = data.ttl_hours or config.default_ttl_hours
        ttl_hours = min(ttl_hours, config.max_ttl_hours)
        now = utc_now()
        expires_at = now + timedelta(hours=ttl_hours)

        # Resolve cost budget
        cost_budget = data.cost_budget_usd
        if cost_budget is None:
            cost_budget = config.default_cost_budget_usd
        if cost_budget is not None:
            cost_budget = min(cost_budget, config.max_cost_budget_usd)

        session = await self._execute_db_operation(
            "create_session",
            self.repo.create(
                user_id=user_id,
                status=SessionStatus.ACTIVE.value,
                goal=data.goal,
                agent_id=data.agent_id,
                cost_budget_usd=cost_budget,
                session_metadata=data.session_metadata or {},
                expires_at=expires_at,
            ),
        )

        self._log_operation(
            "Session created",
            session_id=session.id,
            ttl_hours=ttl_hours,
            cost_budget=cost_budget,
        )

        await self._publish_session_event("session.created", session)
        return session

    async def get_session(self, session_id: str) -> Session:
        """Get a session by ID. Raises NotFoundError if not found."""
        return await self.repo.get_by_id(session_id)

    async def update_session(self, session_id: str, data: SessionUpdate) -> Session:
        """Update mutable session fields."""
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return await self.repo.get_by_id(session_id)

        # Enforce max cost budget
        if "cost_budget_usd" in update_data and update_data["cost_budget_usd"] is not None:
            config = get_app_config().sessions
            update_data["cost_budget_usd"] = min(
                update_data["cost_budget_usd"], config.max_cost_budget_usd
            )

        session = await self._execute_db_operation(
            "update_session",
            self.repo.update(session_id, **update_data),
        )
        return session

    async def list_sessions(
        self,
        user_id: str | None = None,
        status_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Session], int]:
        """List sessions with optional user and status filters. Pagination included."""
        sessions = await self.repo.get_by_user(
            user_id=user_id, status_filter=status_filter, limit=limit, offset=offset
        )
        total = await self.repo.count_by_user(user_id=user_id, status_filter=status_filter)
        return sessions, total

    # --- State Transitions ---

    async def _transition(
        self,
        session_id: str,
        target_status: SessionStatus,
        reason: str | None = None,
    ) -> Session:
        """Transition a session to a new status with state machine validation."""
        session = await self.repo.get_by_id(session_id)
        current = SessionStatus(session.status)

        if target_status not in VALID_TRANSITIONS.get(current, set()):
            raise ValidationError(
                message=f"Cannot transition from {current.value} to {target_status.value}",
                details={"current_status": current.value, "target_status": target_status.value},
            )

        session = await self._execute_db_operation(
            f"session_{target_status.value}",
            self.repo.update(
                session_id,
                status=target_status.value,
                **({"session_metadata": {
                    **(session.session_metadata or {}),
                    f"{target_status.value}_reason": reason,
                }} if reason else {}),
            ),
        )

        self._log_operation(
            f"Session {target_status.value}",
            session_id=session_id,
            from_status=current.value,
            reason=reason,
        )

        await self._publish_session_event(f"session.{target_status.value}", session)
        return session

    async def suspend_session(self, session_id: str, reason: str) -> Session:
        """Suspend a session — waiting for human/AI input or approval."""
        return await self._transition(session_id, SessionStatus.SUSPENDED, reason=reason)

    async def resume_session(self, session_id: str) -> Session:
        """Resume a suspended session."""
        return await self._transition(session_id, SessionStatus.ACTIVE)

    async def complete_session(self, session_id: str) -> Session:
        """Mark a session as completed — goal achieved or user ended."""
        return await self._transition(session_id, SessionStatus.COMPLETED)

    async def fail_session(self, session_id: str, reason: str) -> Session:
        """Mark a session as failed — unrecoverable error."""
        return await self._transition(session_id, SessionStatus.FAILED, reason=reason)

    async def expire_session(self, session_id: str) -> Session:
        """Mark a session as expired — TTL exceeded."""
        return await self._transition(session_id, SessionStatus.EXPIRED, reason="TTL exceeded")

    # --- Cost Tracking ---

    async def update_cost(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        """Add token usage and cost to a session. Does NOT check budget — use enforce_budget() first."""
        session = await self.repo.get_by_id(session_id)
        await self._execute_db_operation(
            "update_cost",
            self.repo.update(
                session_id,
                total_input_tokens=session.total_input_tokens + input_tokens,
                total_output_tokens=session.total_output_tokens + output_tokens,
                total_cost_usd=session.total_cost_usd + cost_usd,
            ),
        )

        self._log_debug(
            "Cost updated",
            session_id=session_id,
            added_cost=cost_usd,
            total_cost=session.total_cost_usd + cost_usd,
        )

        # Check budget warning threshold
        if session.cost_budget_usd:
            new_total = session.total_cost_usd + cost_usd
            config = get_app_config().sessions
            if new_total >= session.cost_budget_usd * config.budget_warning_threshold:
                await self._publish_session_event("session.cost.budget_warning", session)

    async def enforce_budget(
        self,
        session_id: str,
        estimated_cost: float = 0.0,
    ) -> None:
        """Check if a session has budget remaining BEFORE making an LLM call.

        Call this before every LLM invocation. Raises BudgetExceededError if
        the current cost plus estimated cost exceeds the budget.
        """
        session = await self.repo.get_by_id(session_id)
        if session.cost_budget_usd is None:
            return  # Unlimited budget

        projected = session.total_cost_usd + estimated_cost
        if projected >= session.cost_budget_usd:
            raise BudgetExceededError(
                message=(
                    f"Session cost {session.total_cost_usd:.4f} + estimated "
                    f"{estimated_cost:.4f} = {projected:.4f} exceeds budget "
                    f"{session.cost_budget_usd:.4f}"
                ),
                current_cost=session.total_cost_usd,
                budget=session.cost_budget_usd,
            )

    # --- Activity Tracking ---

    async def touch_activity(self, session_id: str) -> None:
        """Update last_activity_at and slide the expiry window."""
        session = await self.repo.get_by_id(session_id)
        if session.expires_at is not None:
            config = get_app_config().sessions
            # Slide the expiry window based on original TTL or default
            ttl_hours = config.default_ttl_hours
            new_expires_at = utc_now() + timedelta(hours=ttl_hours)
            # Clamp to max TTL from original creation
            max_expires = session.created_at + timedelta(hours=config.max_ttl_hours)
            if new_expires_at > max_expires:
                new_expires_at = max_expires
            await self.repo.update_last_activity(session_id, new_expires_at)
        else:
            await self.repo.update_last_activity(session_id)

    # --- Channel Binding ---

    async def bind_channel(
        self,
        session_id: str,
        channel_type: str,
        channel_id: str,
    ) -> SessionChannel:
        """Bind a channel to a session. Deactivates any previous binding for this channel."""
        await self.repo.get_by_id(session_id)  # Verify session exists
        binding = await self._execute_db_operation(
            "bind_channel",
            self.repo.bind_channel(session_id, channel_type, channel_id),
        )
        self._log_operation(
            "Channel bound",
            session_id=session_id,
            channel_type=channel_type,
            channel_id=channel_id,
        )
        return binding

    async def unbind_channel(
        self,
        session_id: str,
        channel_type: str,
        channel_id: str,
    ) -> None:
        """Unbind a channel from a session."""
        await self._execute_db_operation(
            "unbind_channel",
            self.repo.unbind_channel(session_id, channel_type, channel_id),
        )

    async def get_session_by_channel(
        self,
        channel_type: str,
        channel_id: str,
    ) -> Session:
        """Find the active session for a channel. Raises NotFoundError if not found."""
        session = await self.repo.get_session_by_channel(channel_type, channel_id)
        if session is None:
            raise NotFoundError(
                message=f"No active session for {channel_type}:{channel_id}"
            )
        return session

    # --- Messages ---

    async def add_message(
        self,
        session_id: str,
        data: SessionMessageCreate,
    ) -> None:
        """Add a message to a session's conversation history."""
        await self.repo.get_by_id(session_id)  # Verify session exists
        await self._execute_db_operation(
            "add_message",
            self.repo.add_message(
                session_id=session_id,
                role=data.role,
                content=data.content,
                sender_id=data.sender_id,
                model=data.model,
                input_tokens=data.input_tokens,
                output_tokens=data.output_tokens,
                cost_usd=data.cost_usd,
                tool_name=data.tool_name,
                tool_call_id=data.tool_call_id,
            ),
        )

    async def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list, int]:
        """Get messages for a session with pagination."""
        await self.repo.get_by_id(session_id)  # Verify session exists
        messages = await self.repo.get_messages(session_id, limit=limit, offset=offset)
        total = await self.repo.count_messages(session_id)
        return messages, total

    # --- Expired Session Cleanup ---

    async def expire_inactive_sessions(self) -> int:
        """Find and expire sessions past their TTL. Returns count of expired sessions."""
        expired = await self.repo.find_expired()
        count = 0
        for session in expired:
            try:
                await self.expire_session(session.id)
                count += 1
            except ValidationError:
                pass  # Already in terminal state — skip
        if count > 0:
            logger.info(
                "Expired inactive sessions",
                extra={"count": count},
            )
        return count

    # --- Event Publishing ---

    async def _publish_session_event(self, event_type: str, session: Session) -> None:
        """Publish a session lifecycle domain event via the event bus (Phase 1).

        Feature-flag gated via events_publish_enabled. If the event bus is not
        available or disabled, this is a no-op.
        """
        try:
            from modules.backend.core.config import get_app_config

            if not get_app_config().features.events_publish_enabled:
                return

            from modules.backend.events.publishers import EventPublisher
            from modules.backend.events.schemas import EventEnvelope

            envelope = EventEnvelope(
                event_type=event_type,
                source="session-service",
                correlation_id=session.id,
                session_id=session.id,
                payload={
                    "session_id": session.id,
                    "status": session.status,
                    "user_id": session.user_id,
                    "goal": session.goal,
                    "total_cost_usd": session.total_cost_usd,
                    "cost_budget_usd": session.cost_budget_usd,
                },
            )

            publisher = EventPublisher()
            await publisher.publish(
                stream=f"sessions:session-{event_type.split('.')[-1]}",
                event=envelope,
            )
        except Exception as e:
            # Event publishing is non-critical — log and continue
            logger.warning(
                "Failed to publish session event",
                extra={"event_type": event_type, "session_id": session.id, "error": str(e)},
            )
