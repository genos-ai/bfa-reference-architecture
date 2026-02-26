"""
Unit Tests for agent dependency injection (FileScope, BaseAgentDeps).
"""

import pytest

from modules.backend.agents.deps.base import BaseAgentDeps, FileScope


class TestFileScope:
    """Tests for FileScope access control."""

    def test_check_read_allows_matching_path(self):
        scope = FileScope(read_paths=["modules/", "config/"])
        scope.check_read("modules/backend/core/config.py")

    def test_check_read_denies_non_matching_path(self):
        scope = FileScope(read_paths=["modules/"])
        with pytest.raises(PermissionError, match="read access denied"):
            scope.check_read("scripts/something.py")

    def test_check_write_allows_matching_path(self):
        scope = FileScope(write_paths=["modules/backend/"])
        scope.check_write("modules/backend/services/note.py")

    def test_check_write_denies_non_matching_path(self):
        scope = FileScope(write_paths=["modules/backend/"])
        with pytest.raises(PermissionError, match="write access denied"):
            scope.check_write("config/settings/app.yaml")

    def test_check_write_denies_empty_scope(self):
        scope = FileScope(write_paths=[])
        with pytest.raises(PermissionError):
            scope.check_write("anything.py")

    def test_is_readable_returns_true(self):
        scope = FileScope(read_paths=["modules/"])
        assert scope.is_readable("modules/backend/main.py") is True

    def test_is_readable_returns_false(self):
        scope = FileScope(read_paths=["modules/"])
        assert scope.is_readable("scripts/foo.py") is False

    def test_wildcard_star_allows_everything(self):
        scope = FileScope(read_paths=["*"])
        scope.check_read("anything/anywhere/file.py")

    def test_extension_wildcard(self):
        scope = FileScope(read_paths=["*.py"])
        scope.check_read("cli.py")

    def test_extension_wildcard_denies_non_match(self):
        scope = FileScope(read_paths=["*.py"])
        with pytest.raises(PermissionError):
            scope.check_read("config/settings/app.yaml")

    def test_trailing_slash_handling(self):
        scope = FileScope(read_paths=["scripts"])
        assert scope.is_readable("scripts/foo.py") is True
