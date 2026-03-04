"""Session repository — database queries for sessions and related tables."""

from datetime import datetime

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.utils import utc_now
from modules.backend.models.session import (
    Session,
    SessionChannel,
    SessionMessage,
    SessionStatus,
)
from modules.backend.repositories.base import BaseRepository


class SessionRepository(BaseRepository[Session]):
    """Repository for Session model with lifecycle and channel queries."""

    model = Session

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_active_by_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """Get active and suspended sessions for a user."""
        result = await self.session.execute(
            select(Session)
            .where(
                Session.user_id == user_id,
                Session.status.in_([
                    SessionStatus.ACTIVE.value,
                    SessionStatus.SUSPENDED.value,
                ]),
            )
            .order_by(Session.last_activity_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_user(
        self,
        user_id: str | None = None,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """Get sessions, optionally filtered by user and/or status."""
        stmt = select(Session)
        if user_id is not None:
            stmt = stmt.where(Session.user_id == user_id)
        if status_filter:
            stmt = stmt.where(Session.status == status_filter)
        stmt = stmt.order_by(Session.last_activity_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_user(
        self,
        user_id: str | None = None,
        status_filter: str | None = None,
    ) -> int:
        """Count sessions, optionally filtered by user and/or status."""
        stmt = select(func.count()).select_from(Session)
        if user_id is not None:
            stmt = stmt.where(Session.user_id == user_id)
        if status_filter:
            stmt = stmt.where(Session.status == status_filter)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def update_last_activity(self, session_id: str, new_expires_at: datetime | None = None) -> None:
        """Touch the session's last_activity_at and optionally update expires_at."""
        values: dict = {"last_activity_at": utc_now()}
        if new_expires_at is not None:
            values["expires_at"] = new_expires_at
        await self.session.execute(
            update(Session).where(Session.id == session_id).values(**values)
        )
        await self.session.flush()

    async def find_expired(self, now: datetime | None = None) -> list[Session]:
        """Find sessions past their expires_at that are still ACTIVE or SUSPENDED."""
        if now is None:
            now = utc_now()
        result = await self.session.execute(
            select(Session).where(
                Session.expires_at.isnot(None),
                Session.expires_at <= now,
                Session.status.in_([
                    SessionStatus.ACTIVE.value,
                    SessionStatus.SUSPENDED.value,
                ]),
            )
        )
        return list(result.scalars().all())

    # --- Channel queries ---

    async def bind_channel(
        self,
        session_id: str,
        channel_type: str,
        channel_id: str,
    ) -> SessionChannel:
        """Bind a channel to a session. Deactivates any existing binding for this channel."""
        # Deactivate existing bindings for this channel
        await self.session.execute(
            update(SessionChannel)
            .where(
                SessionChannel.channel_type == channel_type,
                SessionChannel.channel_id == channel_id,
                SessionChannel.is_active == True,  # noqa: E712
            )
            .values(is_active=False)
        )

        binding = SessionChannel(
            session_id=session_id,
            channel_type=channel_type,
            channel_id=channel_id,
        )
        self.session.add(binding)
        await self.session.flush()
        await self.session.refresh(binding)
        return binding

    async def unbind_channel(
        self,
        session_id: str,
        channel_type: str,
        channel_id: str,
    ) -> None:
        """Deactivate a channel binding."""
        await self.session.execute(
            update(SessionChannel)
            .where(
                SessionChannel.session_id == session_id,
                SessionChannel.channel_type == channel_type,
                SessionChannel.channel_id == channel_id,
                SessionChannel.is_active == True,  # noqa: E712
            )
            .values(is_active=False)
        )
        await self.session.flush()

    async def get_session_by_channel(
        self,
        channel_type: str,
        channel_id: str,
    ) -> Session | None:
        """Find the active session bound to a channel. Returns None if not found."""
        result = await self.session.execute(
            select(Session)
            .join(
                SessionChannel,
                SessionChannel.session_id == Session.id,
            )
            .where(
                SessionChannel.channel_type == channel_type,
                SessionChannel.channel_id == channel_id,
                SessionChannel.is_active == True,  # noqa: E712
                Session.status.in_([
                    SessionStatus.ACTIVE.value,
                    SessionStatus.SUSPENDED.value,
                ]),
            )
        )
        return result.scalar_one_or_none()

    # --- Message queries ---

    async def add_message(self, **kwargs) -> SessionMessage:
        """Add a message to a session."""
        msg = SessionMessage(**kwargs)
        self.session.add(msg)
        await self.session.flush()
        await self.session.refresh(msg)
        return msg

    async def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SessionMessage]:
        """Get messages for a session, ordered by creation time."""
        result = await self.session.execute(
            select(SessionMessage)
            .where(SessionMessage.session_id == session_id)
            .order_by(SessionMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_messages(self, session_id: str) -> int:
        """Count messages in a session."""
        result = await self.session.execute(
            select(func.count())
            .select_from(SessionMessage)
            .where(SessionMessage.session_id == session_id)
        )
        return result.scalar_one()
