"""
Agent dependency injection base classes.

Provides BaseAgentDeps (common to all agents), FileScope (filesystem
access control), and agent-specific deps dataclasses. Deps are constructed
from YAML config at invocation time and injected into PydanticAI RunContext.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FileScope:
    """Defines which filesystem paths an agent can read and write.

    Configured per agent in YAML under ``scope.read`` and ``scope.write``.
    Enforced in shared tool implementations before any file operation.
    """

    read_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)

    def check_read(self, rel_path: str) -> None:
        """Raise PermissionError if the path is not in the read scope."""
        if not self._matches(rel_path, self.read_paths):
            raise PermissionError(f"Agent read access denied: {rel_path}")

    def check_write(self, rel_path: str) -> None:
        """Raise PermissionError if the path is not in the write scope."""
        if not self._matches(rel_path, self.write_paths):
            raise PermissionError(f"Agent write access denied: {rel_path}")

    def is_readable(self, rel_path: str) -> bool:
        """Check if a path is within read scope without raising."""
        return self._matches(rel_path, self.read_paths)

    def _matches(self, rel_path: str, allowed: list[str]) -> bool:
        for pattern in allowed:
            if pattern == "*":
                return True
            if pattern.startswith("*.") and rel_path.endswith(pattern[1:]):
                return True
            normalized = pattern.rstrip("/")
            if rel_path == normalized or rel_path.startswith(normalized + "/"):
                return True
        return False


@dataclass
class BaseAgentDeps:
    """Common dependencies injected into every agent at runtime."""

    project_root: Path
    scope: FileScope
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class QaAgentDeps(BaseAgentDeps):
    """QA compliance agent deps — adds progress callback for streaming."""

    on_progress: Any = None

    def emit(self, event: dict) -> None:
        """Emit a progress event if a callback is registered."""
        if self.on_progress is not None:
            self.on_progress(event)


@dataclass
class HealthAgentDeps(BaseAgentDeps):
    """Health agent deps — adds application config for metadata tools."""

    app_config: Any = None


@dataclass
class HorizontalAgentDeps(BaseAgentDeps):
    """Horizontal (supervisory) agent deps — adds delegation authority."""

    allowed_agents: set[str] = field(default_factory=set)
    max_delegation_depth: int = 0
    coordinator: Any = None
