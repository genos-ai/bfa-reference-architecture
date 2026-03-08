"""Tests for mission API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from modules.backend.api.v1.endpoints.missions import router
from modules.backend.core.exceptions import NotFoundError


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router, prefix="/missions")

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    return app


@pytest.fixture
def mock_db_session():
    return AsyncMock()


@pytest.fixture
async def client(app, mock_db_session):
    from modules.backend.core.database import get_db_session

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_db_session] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestListMissions:
    @pytest.mark.asyncio
    async def test_list_missions_returns_200(self, client):
        with patch(
            "modules.backend.api.v1.endpoints.missions.MissionPersistenceService",
        ) as MockService:
            instance = MockService.return_value
            instance.list_missions = AsyncMock(return_value=([], 0))

            response = await client.get("/missions")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    @pytest.mark.asyncio
    async def test_list_missions_with_filters(self, client):
        with patch(
            "modules.backend.api.v1.endpoints.missions.MissionPersistenceService",
        ) as MockService:
            instance = MockService.return_value
            instance.list_missions = AsyncMock(return_value=([], 0))

            response = await client.get(
                "/missions?status=completed&roster_name=research",
            )
            assert response.status_code == 200


class TestGetMission:
    @pytest.mark.asyncio
    async def test_get_mission_not_found(self, client):
        with patch(
            "modules.backend.api.v1.endpoints.missions.MissionPersistenceService",
        ) as MockService:
            instance = MockService.return_value
            instance.get_mission = AsyncMock(return_value=None)

            response = await client.get("/missions/nonexistent")
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_mission_found(self, client):
        mock_mission = MagicMock()
        mock_mission.id = "m-123"
        mock_mission.session_id = "s-123"
        mock_mission.roster_name = "default"
        mock_mission.status = "completed"
        mock_mission.total_cost_usd = 0.05
        mock_mission.started_at = "2026-03-06T00:00:00"
        mock_mission.completed_at = "2026-03-06T00:01:00"
        mock_mission.parent_mission_id = None
        mock_mission.created_at = "2026-03-06T00:00:00"
        mock_mission.updated_at = "2026-03-06T00:01:00"
        mock_mission.objective_statement = None
        mock_mission.objective_category = None
        mock_mission.task_plan_json = {}
        mock_mission.mission_outcome_json = {}
        mock_mission.planning_thinking_trace = None
        mock_mission.task_executions = []
        mock_mission.decisions = []

        with patch(
            "modules.backend.api.v1.endpoints.missions.MissionPersistenceService",
        ) as MockService:
            instance = MockService.return_value
            instance.get_mission = AsyncMock(return_value=mock_mission)

            response = await client.get("/missions/m-123")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True


class TestGetMissionCost:
    @pytest.mark.asyncio
    async def test_get_cost_breakdown(self, client):
        from modules.backend.schemas.mission_record import MissionCostBreakdown

        breakdown = MissionCostBreakdown(
            mission_id="m-123",
            total_cost_usd=0.10,
            task_costs=[],
            model_costs={},
            attempt_count=0,
            total_input_tokens=200,
            total_output_tokens=100,
        )

        with patch(
            "modules.backend.api.v1.endpoints.missions.MissionPersistenceService",
        ) as MockService:
            instance = MockService.return_value
            instance.get_cost_breakdown = AsyncMock(return_value=breakdown)

            response = await client.get("/missions/m-123/cost")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["total_cost_usd"] == 0.10
