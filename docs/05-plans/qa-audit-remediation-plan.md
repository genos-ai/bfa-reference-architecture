# QA Execution Plan

## Run Metadata
- **Date:** 2026-02-26
- **Codebase Root:** `/Users/herman.young/development/bfa_reference_architecture`
- **Entry Points Scanned:** `cli.py`, `chat.py`, `tui.py`
- **Total Files Reviewed:** 155 (145 Python, 6 YAML configs, `.env`, `.gitignore`, `AGENTS.md`, `README.md`)
- **Total Findings:** CRITICAL: 0 | HIGH: 2 | MEDIUM: 2 | LOW: 0
- **Revision Note:** `scripts/dead_code_detector.py` deleted by owner — PATTERN-01 and findings #1–#9, #12–#13 from original audit removed. Remaining findings renumbered.

---

## Systemic Patterns
> Root causes that drive multiple findings below. Read before executing any fix.

- **[PATTERN-01]** Every unit test file (15 files) uses `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`) to mock internal dependencies. The QA ruleset requires tests to exercise real code against the real platform, targeting public interfaces (black-box). This affects the entire `tests/unit/` tree. Drives finding #2.

---

## Findings

| # | Criticality | File(s) | Line(s) | Rule Violated | Current Behaviour | Expected Behaviour | Pattern Ref |
|---|-------------|---------|---------|---------------|-------------------|-------------------|-------------|
| 1 | HIGH | `cli.py` | L597, L634 | Project root via `.project_root` | `PROJECT_ROOT = Path(__file__).parent` used for alembic.ini path construction and `cwd` in `run_migrations()` | Use `find_project_root()` from `modules.backend.core.config` for all path construction after bootstrapping | — |
| 2 | HIGH | 15 files in `tests/unit/` | Various | No mocked tests; black-box testing | `from unittest.mock import MagicMock, AsyncMock, patch` in: `test_config.py`, `test_exception_handlers.py`, `test_logging.py`, `test_middleware.py`, `test_pagination.py`, `test_security.py`, `test_health.py`, `test_note_service.py`, `test_base_service.py`, `test_startup_checks.py`, `test_rate_limiter.py`, `test_adapters.py`, `test_middlewares.py`, `test_notifications.py`, `conftest.py` | Tests must exercise real code against the real platform; replace mocks with real implementations or move to integration tests | PATTERN-01 |
| 3 | MEDIUM | `config/settings/application.yaml` | L1–27 | YAML files must have commented list of all options at top | Comment header lists `telegram.webhook_path` and `telegram.authorized_users` but omits `telegram.max_message_length` | Add `#     max_message_length - Maximum message length (integer, default: 4096)` to the comment header | — |
| 4 | MEDIUM | `tests/unit/backend/repositories/` | — | Every public module interface must have tests | Directory exists with empty `__init__.py` but contains no test files; `NoteRepository` and `BaseRepository` have zero dedicated tests | Add test files covering the public interfaces of `BaseRepository` and `NoteRepository` | — |

---

## Execution Order

> Dependency-sequenced. The coding agent must not skip ahead. Some fixes will break others if done out of order.

1. **Finding #1** ✅ DONE — Replaced `PROJECT_ROOT` with `find_project_root()` in `cli.py` for alembic.ini path (L596) and migration cwd (L633). Bootstrap assignment at L26 unchanged.

2. **Finding #3** ✅ DONE — Added `max_message_length` to application.yaml comment header. Also fixed `authorized_users` comment from "empty = allow all" to "empty = deny all" per P8.

3. **Finding #4** ✅ DONE — Added 22 repository tests to `tests/unit/backend/repositories/test_note_repository.py`. No mocks — uses real in-memory SQLite via conftest `db_session` fixture. Covers full CRUD (create, read, update, delete, exists, count) plus note-specific methods (get_all_active, get_archived, archive, unarchive, search_by_title, count_active).

4. **[PATTERN-01] Finding #2** — DEFERRED. Systemic rewrite of 15 test files to remove mocks. This is a separate effort requiring file-by-file analysis — each test must be evaluated for whether it can run against real infrastructure (in-memory SQLite, real config loading) or must move to `tests/integration/`. All other findings (#1, #3, #4) are resolved. This item is tracked separately.

---

## Out of Scope

> Findings intentionally excluded from this execution run and why.

| # | Criticality | File(s) | Reason Excluded |
|---|-------------|---------|-----------------|
| — | LOW | `modules/backend/core/logging.py` L40 | `import logging` is required — this IS the centralized logging module; it must import stdlib logging to configure it |
| — | LOW | `modules/backend/migrations/env.py` L10 | `from logging.config import fileConfig` is standard Alembic boilerplate required by the framework |
| — | LOW | `cli.py` L26–27, `chat.py` L25–26, `tui.py` L19–20 | `PROJECT_ROOT = Path(__file__).parent` + `sys.path.insert` for bootstrapping is necessary — `find_project_root()` cannot be called before the import path is configured. Only flagged in #1 where `PROJECT_ROOT` is reused after bootstrapping |
| — | LOW | `modules/backend/core/logging.py` L51 | `VALID_SOURCES = frozenset({...})` — this is a validation constant, not a configurable value; it defines the protocol contract for log source fields |
| — | LOW | `cli.py` L32 | `LONG_RUNNING_SERVICES = {"server", ...}` — this is a code-structural constant mapping CLI service names to behaviour, not a configurable value |
| — | INFO | Test fixture files (`test_code_qa.py` L35, `test_compliance.py` L30) | Lines containing `from .sibling import something` and `import logging` are intentional test fixtures written to temp files for compliance scanner testing — not actual code violations |
