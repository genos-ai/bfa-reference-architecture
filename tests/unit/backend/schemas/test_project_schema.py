"""Tests for Project schemas."""

import pytest
from pydantic import ValidationError

from modules.backend.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)


class TestProjectCreate:
    def test_valid_minimal(self):
        schema = ProjectCreate(
            name="my-project",
            description="A test project",
            owner_id="user:test",
        )
        assert schema.name == "my-project"
        assert schema.default_roster == "default"

    def test_valid_full(self):
        schema = ProjectCreate(
            name="full-project",
            description="Full project",
            owner_id="user:test",
            team_id="team-alpha",
            default_roster="research",
            budget_ceiling_usd=50.0,
            repo_url="https://github.com/test/repo",
            repo_root="/home/test/repo",
        )
        assert schema.budget_ceiling_usd == 50.0

    def test_invalid_name_uppercase(self):
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="MyProject",
                description="Bad name",
                owner_id="user:test",
            )

    def test_invalid_name_starts_with_number(self):
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="1project",
                description="Bad name",
                owner_id="user:test",
            )

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="",
                description="No name",
                owner_id="user:test",
            )

    def test_budget_must_be_positive(self):
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="cheap-project",
                description="Negative budget",
                owner_id="user:test",
                budget_ceiling_usd=0.0,
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="strict-project",
                description="No extras",
                owner_id="user:test",
                unknown_field="bad",
            )


class TestProjectUpdate:
    def test_all_none(self):
        schema = ProjectUpdate()
        assert schema.description is None
        assert schema.status is None

    def test_valid_status(self):
        schema = ProjectUpdate(status="paused")
        assert schema.status == "paused"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            ProjectUpdate(status="deleted")


class TestProjectResponse:
    def test_from_dict(self):
        resp = ProjectResponse(
            id="abc-123",
            name="resp-project",
            description="Response test",
            status="active",
            owner_id="user:test",
            team_id=None,
            default_roster="default",
            budget_ceiling_usd=None,
            repo_url=None,
            repo_root=None,
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-01T00:00:00",
        )
        assert resp.id == "abc-123"
        assert resp.name == "resp-project"
