"""
Shared agent output schemas.

Pydantic models used as ``output_type`` on PydanticAI agents.
Defined here (not in agent files) so they can be imported by tests,
API endpoints, and other consumers without importing agent internals.
"""

from pydantic import BaseModel


class Violation(BaseModel):
    """A single compliance violation found during audit."""

    rule_id: str
    file: str
    line: int | None = None
    message: str
    severity: str
    recommendation: str | None = None


class QaAuditResult(BaseModel):
    """Structured output from the QA compliance agent (read-only audit)."""

    summary: str
    total_violations: int
    error_count: int
    warning_count: int
    violations: list[Violation]
    scanned_files_count: int


class HealthCheckResult(BaseModel):
    """Structured output from the system health agent."""

    summary: str
    components: dict[str, str]
    advice: str | None = None
