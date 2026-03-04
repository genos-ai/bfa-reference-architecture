"""
Unit Tests for mission_control.collect().

Per P12: real PostgreSQL (db_session with rollback), real config/registry,
TestModel for LLM (the only mock — we don't operate LLM providers).

collect() is a convenience wrapper that buffers handle() events into a dict.
"""

from unittest.mock import patch

import pytest
from pydantic_ai.models.test import TestModel

from modules.backend.agents.mission_control.mission_control import collect
from modules.backend.schemas.session import SessionCreate
from modules.backend.services.session import SessionService


@pytest.fixture
def session_service(db_session):
    return SessionService(db_session)


@pytest.fixture
async def health_session(session_service):
    return await session_service.create_session(
        SessionCreate(goal="test collect", agent_id="system.health.agent"),
    )


@pytest.fixture(autouse=True)
def _reset_registry():
    from modules.backend.agents.mission_control.registry import get_registry

    get_registry().reset()
    yield
    get_registry().reset()


def _patch_build_model():
    return patch(
        "modules.backend.agents.mission_control.mission_control._build_model",
        return_value=TestModel(call_tools=[]),
    )


class TestCollect:
    """Tests for collect() convenience function."""

    @pytest.mark.asyncio
    async def test_returns_agent_name(self, session_service, health_session):
        with _patch_build_model():
            result = await collect(
                str(health_session.id), "check health", session_service=session_service,
            )
        assert result["agent_name"] == "system.health.agent"

    @pytest.mark.asyncio
    async def test_returns_output(self, session_service, health_session):
        with _patch_build_model():
            result = await collect(
                str(health_session.id), "check health", session_service=session_service,
            )
        assert isinstance(result["output"], str)

    @pytest.mark.asyncio
    async def test_returns_cost(self, session_service, health_session):
        with _patch_build_model():
            result = await collect(
                str(health_session.id), "check health", session_service=session_service,
            )
        assert isinstance(result["cost_usd"], float)
        assert result["cost_usd"] >= 0

    @pytest.mark.asyncio
    async def test_returns_session_id(self, session_service, health_session):
        sid = str(health_session.id)
        with _patch_build_model():
            result = await collect(sid, "check health", session_service=session_service)
        assert result["session_id"] == sid
