# QA Execution Plan

## Run Metadata
- **Date:** 2026-02-26
- **Codebase Root:** `/Users/herman.young/development/bfa_reference_architecture`
- **Entry Points Scanned:** `cli.py`, `chat.py`, `tui.py`
- **Total Files Reviewed:** 155 (145 Python, 6 YAML configs, `.env`, `.gitignore`, `AGENTS.md`, `README.md`)
- **Total Findings:** CRITICAL: 0 | HIGH: 1 | MEDIUM: 0 | LOW: 0
- **Revision Note:** `scripts/dead_code_detector.py` deleted by owner — PATTERN-01 and findings #1–#9, #12–#13 from original audit removed. Findings #1, #3, #4 from revised plan verified fixed. Only finding #2 (test mocking) remains open.

---

## Systemic Patterns
> Root causes that drive multiple findings below. Read before executing any fix.

- **[PATTERN-01]** Every unit test file (15 files) uses `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`) to mock internal dependencies. The QA ruleset requires tests to exercise real code against the real platform, targeting public interfaces (black-box). This affects the entire `tests/unit/` tree. Drives finding #1.

---

## Findings

### Resolved

| # | Criticality | File(s) | Status | Resolution |
|---|-------------|---------|--------|------------|
| ~~1~~ | ~~HIGH~~ | ~~`cli.py`~~ | **RESOLVED** | `PROJECT_ROOT` replaced with `find_project_root()` at L596 and L633. Bootstrapping use at L25–26 retained as expected. |
| ~~3~~ | ~~MEDIUM~~ | ~~`config/settings/application.yaml`~~ | **RESOLVED** | `max_message_length` added to the commented option header under the `telegram` section (L27). |
| ~~4~~ | ~~MEDIUM~~ | ~~`tests/unit/backend/repositories/`~~ | **RESOLVED** | `test_note_repository.py` added covering `NoteRepository` public interface. |

### Open

| # | Criticality | File(s) | Line(s) | Rule Violated | Current Behaviour | Expected Behaviour | Pattern Ref |
|---|-------------|---------|---------|---------------|-------------------|-------------------|-------------|
| 2 | HIGH | 15 files in `tests/unit/` | Various | No mocked tests; black-box testing | `from unittest.mock import MagicMock, AsyncMock, patch` in: `test_config.py`, `test_exception_handlers.py`, `test_logging.py`, `test_middleware.py`, `test_pagination.py`, `test_security.py`, `test_health.py`, `test_note_service.py`, `test_base_service.py`, `test_startup_checks.py`, `test_rate_limiter.py`, `test_adapters.py`, `test_middlewares.py`, `test_notifications.py`, `conftest.py` | Tests must exercise real code against the real platform; replace mocks with real implementations or move to integration tests | PATTERN-01 |

---

## Execution Order

> Dependency-sequenced. The coding agent must not skip ahead.

1. **[PATTERN-01] Finding #2** — Audit all 15 unit test files using `unittest.mock`. For each, determine whether the mocked functionality can be replaced with real execution. Tests that require external infrastructure (database, Redis, Anthropic API) should be moved to `tests/integration/` or `tests/e2e/`. Tests that mock purely for isolation where real code can run should have mocks removed. This is a large-scope refactoring effort and should be done file-by-file.

---

## Out of Scope

> Findings intentionally excluded from this execution run and why.

| # | Criticality | File(s) | Reason Excluded |
|---|-------------|---------|-----------------|
| — | LOW | `modules/backend/core/logging.py` L40 | `import logging` is required — this IS the centralized logging module; it must import stdlib logging to configure it |
| — | LOW | `modules/backend/migrations/env.py` L10 | `from logging.config import fileConfig` is standard Alembic boilerplate required by the framework |
| — | LOW | `cli.py` L25–26, `chat.py` L25–26, `tui.py` L19–20 | `PROJECT_ROOT = Path(__file__).parent` + `sys.path.insert` for bootstrapping is necessary — `find_project_root()` cannot be called before the import path is configured |
| — | LOW | `modules/backend/core/logging.py` L51 | `VALID_SOURCES = frozenset({...})` — this is a validation constant, not a configurable value; it defines the protocol contract for log source fields |
| — | LOW | `cli.py` L32 | `LONG_RUNNING_SERVICES = {"server", ...}` — this is a code-structural constant mapping CLI service names to behaviour, not a configurable value |
| — | INFO | Test fixture files (`test_code_qa.py` L35, `test_compliance.py` L30) | Lines containing `from .sibling import something` and `import logging` are intentional test fixtures written to temp files for compliance scanner testing — not actual code violations |
