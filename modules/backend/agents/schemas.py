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


class ArchitectureFinding(BaseModel):
    """A single architectural principle violation found during review."""

    principle: str         # unnecessary_complexity, unsafe_concurrency, etc.
    file: str
    line: int | None = None
    message: str
    recommendation: str
    related_files: list[str] = []


class ArchitectureReviewResult(BaseModel):
    """Structured output from the architecture review agent (read-only)."""

    summary: str
    total_findings: int
    findings: list[ArchitectureFinding]
    files_reviewed: int
    new_findings: int      # findings not in baseline
    baseline_findings: int  # known findings from baseline


class HealthFinding(BaseModel):
    """A single issue found during health check."""

    category: str          # log_errors, config, dependencies, file_structure
    severity: str          # error, warning, info
    message: str
    details: str | None = None


class HealthCheckResult(BaseModel):
    """Structured output from the system health agent (read-only)."""

    summary: str
    overall_status: str    # healthy, degraded, unhealthy
    findings: list[HealthFinding]
    error_count: int
    warning_count: int
    checks_performed: list[str]
