"""
Unit Tests for shared filesystem tool implementations.

Tests use real temporary files — no mocks.
"""

import pytest

from modules.backend.agents.deps.base import FileScope
from modules.backend.agents.tools.filesystem import list_files, read_file


@pytest.fixture
def sample_project(tmp_path):
    """Create a temp project with sample files."""
    modules_dir = tmp_path / "modules" / "backend"
    modules_dir.mkdir(parents=True)
    (modules_dir / "main.py").write_text("app = FastAPI()\n")
    (modules_dir / "__init__.py").write_text("")

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "helper.py").write_text("print('hello')\n")

    return tmp_path


class TestReadFile:
    """Tests for filesystem.read_file."""

    @pytest.mark.asyncio
    async def test_reads_file_within_scope(self, sample_project):
        scope = FileScope(read_paths=["modules/"])
        result = await read_file(sample_project, "modules/backend/main.py", scope)
        assert "FastAPI" in result
        assert "   1|" in result

    @pytest.mark.asyncio
    async def test_denies_file_outside_scope(self, sample_project):
        scope = FileScope(read_paths=["modules/"])
        with pytest.raises(PermissionError, match="read access denied"):
            await read_file(sample_project, "scripts/helper.py", scope)

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_file(self, sample_project):
        scope = FileScope(read_paths=["*"])
        result = await read_file(sample_project, "nonexistent.py", scope)
        assert "Error: file not found" in result


class TestListFiles:
    """Tests for filesystem.list_files."""

    @pytest.mark.asyncio
    async def test_lists_files_within_scope(self, sample_project):
        scope = FileScope(read_paths=["modules/"])
        files = await list_files(sample_project, scope)
        assert any("modules/backend/main.py" in f for f in files)
        assert not any("scripts/" in f for f in files)

    @pytest.mark.asyncio
    async def test_respects_exclusions(self, sample_project):
        scope = FileScope(read_paths=["*"])
        files = await list_files(sample_project, scope, exclusion_paths={"scripts/"})
        assert not any("scripts/" in f for f in files)
