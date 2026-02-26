"""Agent dependency injection — base deps, file scope, agent-specific deps."""

from modules.backend.agents.deps.base import (
    BaseAgentDeps,
    FileScope,
    HealthAgentDeps,
    HorizontalAgentDeps,
    QaAgentDeps,
)

__all__ = [
    "BaseAgentDeps",
    "FileScope",
    "HealthAgentDeps",
    "HorizontalAgentDeps",
    "QaAgentDeps",
]
