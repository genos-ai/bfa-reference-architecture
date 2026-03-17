"""Tests for ContextAssembler.

Tests use mocked dependencies (ProjectContextManager, HistoryQueryService)
since the assembler is pure orchestration over those services.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from modules.backend.core.utils import estimate_tokens
from modules.backend.services.context_assembler import (
    ContextAssembler,
    DEFAULT_TOKEN_BUDGET,
    _CODING_TAGS,
)


@pytest.fixture
def mock_context_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.get_context = AsyncMock(return_value={
        "identity": {"name": "test-project", "tech_stack": ["python"]},
        "version": 1,
    })
    return mgr


@pytest.fixture
def mock_history_service() -> MagicMock:
    svc = MagicMock()
    svc.get_recent_failures = AsyncMock(return_value=[])
    svc.get_recent_task_executions = AsyncMock(return_value=[])
    return svc


@pytest.fixture
def assembler(mock_context_manager, mock_history_service) -> ContextAssembler:
    return ContextAssembler(mock_context_manager, mock_history_service)


class TestEstimateTokens:
    def test_string_input(self):
        assert estimate_tokens("hello world") == len("hello world") // 4

    def test_dict_input(self):
        data = {"key": "value"}
        tokens = estimate_tokens(data)
        assert tokens > 0

    def test_empty_dict(self):
        assert estimate_tokens({}) == len("{}") // 4


class TestBuild:
    @pytest.mark.asyncio
    async def test_includes_pcd_and_task(self, assembler, mock_context_manager):
        """Layer 0 (PCD) and Layer 1 (task) are always present."""
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1", "agent": "analyzer"},
            resolved_inputs={"query": "test"},
        )
        assert "project_context" in packet
        assert packet["project_context"]["identity"]["name"] == "test-project"
        assert packet["task"]["task_id"] == "t1"
        assert packet["inputs"]["query"] == "test"
        mock_context_manager.get_context.assert_called_once_with("proj-1")

    @pytest.mark.asyncio
    async def test_no_history_without_domain_tags(self, assembler, mock_history_service):
        """Layer 2 (history) is skipped when no domain_tags provided."""
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1"},
            resolved_inputs={},
        )
        assert "history" not in packet
        mock_history_service.get_recent_failures.assert_not_called()

    @pytest.mark.asyncio
    async def test_history_included_with_domain_tags(
        self, assembler, mock_history_service,
    ):
        """Layer 2 (history) is assembled when domain_tags are provided."""
        mock_history_service.get_recent_failures = AsyncMock(return_value=[
            {"task_id": "old-t1", "failure_reason": "timeout"},
        ])
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1"},
            resolved_inputs={},
            domain_tags=["auth"],
        )
        assert "history" in packet
        assert "recent_failures" in packet["history"]
        mock_history_service.get_recent_failures.assert_called_once()

    @pytest.mark.asyncio
    async def test_history_executions_included(
        self, assembler, mock_history_service,
    ):
        """Recent executions appear in history when budget allows."""
        mock_history_service.get_recent_task_executions = AsyncMock(
            return_value=[
                {"task_id": "prev-1", "agent_name": "analyzer", "status": "completed"},
            ],
        )
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1"},
            resolved_inputs={},
            domain_tags=["api"],
        )
        assert "history" in packet
        assert "recent_executions" in packet["history"]

    @pytest.mark.asyncio
    async def test_inputs_summarized_when_over_budget(self, assembler):
        """Large non-scalar inputs are summarized when they exceed budget."""
        # Use a list (non-scalar) so the summarizer replaces it with a placeholder
        large_inputs = {"data": list(range(10_000))}
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1"},
            resolved_inputs=large_inputs,
            token_budget=500,  # very tight budget
        )
        assert "inputs" in packet
        assert "<list" in str(packet["inputs"]["data"])

    @pytest.mark.asyncio
    async def test_custom_token_budget(self, assembler):
        """Token budget is respected."""
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1"},
            resolved_inputs={},
            token_budget=100,
        )
        # Should still have PCD and task (never trimmed)
        assert "project_context" in packet
        assert "task" in packet

    @pytest.mark.asyncio
    async def test_default_token_budget(self):
        """Default token budget is set to expected value."""
        assert DEFAULT_TOKEN_BUDGET == 50_000

    @pytest.mark.asyncio
    async def test_history_skipped_when_budget_exhausted(
        self, assembler, mock_history_service,
    ):
        """History is skipped when remaining budget is too low."""
        # Use a very tight budget that PCD+task will consume
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1", "extra": "x" * 2000},
            resolved_inputs={},
            domain_tags=["api"],
            token_budget=50,  # very tight — PCD + task alone exceed it
        )
        # History service should not be called when budget is negative
        assert "history" not in packet


class TestIsCodingTask:
    """Test the domain_tags → coding task classification."""

    def test_none_tags_returns_true(self):
        assert ContextAssembler._is_coding_task(None) is True

    def test_empty_tags_returns_true(self):
        assert ContextAssembler._is_coding_task([]) is True

    def test_coding_tag_returns_true(self):
        for tag in _CODING_TAGS:
            assert ContextAssembler._is_coding_task([tag]) is True

    def test_non_coding_tag_returns_false(self):
        assert ContextAssembler._is_coding_task(["analysis"]) is False
        assert ContextAssembler._is_coding_task(["health"]) is False

    def test_mixed_tags_with_coding(self):
        assert ContextAssembler._is_coding_task(["auth", "bugfix"]) is True

    def test_mixed_tags_without_coding(self):
        assert ContextAssembler._is_coding_task(["auth", "monitoring"]) is False


class TestCodeMapLayer:
    """Test Layer 3 (Code Map) integration in ContextAssembler."""

    @pytest.mark.asyncio
    async def test_no_code_map_without_loader(
        self, mock_context_manager, mock_history_service,
    ):
        """No code_map in packet when no loader is injected."""
        assembler = ContextAssembler(mock_context_manager, mock_history_service)
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1"},
            resolved_inputs={},
            domain_tags=["code"],
        )
        assert "code_map" not in packet

    @pytest.mark.asyncio
    async def test_code_map_included_for_coding_task(
        self, mock_context_manager, mock_history_service,
    ):
        """Code Map markdown is included for coding tasks."""
        mock_loader = MagicMock()
        mock_loader.get_markdown.return_value = "# Code Map\n\n- module_a\n- module_b"

        assembler = ContextAssembler(
            mock_context_manager, mock_history_service,
            code_map_loader=mock_loader,
        )
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1"},
            resolved_inputs={},
            domain_tags=["code"],
        )
        assert "code_map" in packet
        assert "# Code Map" in packet["code_map"]
        mock_loader.get_markdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_code_map_skipped_for_non_coding_task(
        self, mock_context_manager, mock_history_service,
    ):
        """Code Map is not loaded for non-coding domain tags."""
        mock_loader = MagicMock()
        mock_loader.get_markdown.return_value = "# Code Map"

        assembler = ContextAssembler(
            mock_context_manager, mock_history_service,
            code_map_loader=mock_loader,
        )
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1"},
            resolved_inputs={},
            domain_tags=["analysis"],
        )
        assert "code_map" not in packet
        mock_loader.get_markdown.assert_not_called()

    @pytest.mark.asyncio
    async def test_code_map_included_when_no_domain_tags(
        self, mock_context_manager, mock_history_service,
    ):
        """Conservative: Code Map is included when domain_tags is None."""
        mock_loader = MagicMock()
        mock_loader.get_markdown.return_value = "# Code Map\n\nfull content"

        assembler = ContextAssembler(
            mock_context_manager, mock_history_service,
            code_map_loader=mock_loader,
        )
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1"},
            resolved_inputs={},
        )
        assert "code_map" in packet

    @pytest.mark.asyncio
    async def test_code_map_none_when_loader_returns_none(
        self, mock_context_manager, mock_history_service,
    ):
        """No code_map key when loader returns None (file missing)."""
        mock_loader = MagicMock()
        mock_loader.get_markdown.return_value = None

        assembler = ContextAssembler(
            mock_context_manager, mock_history_service,
            code_map_loader=mock_loader,
        )
        packet = await assembler.build(
            project_id="proj-1",
            task_definition={"task_id": "t1"},
            resolved_inputs={},
            domain_tags=["code"],
        )
        assert "code_map" not in packet
