# QA Execution Plan

## Run Metadata
- **Date:** 2026-02-26
- **Codebase Root:** `/Users/herman.young/development/bfa_reference_architecture`
- **Entry Points Scanned:** `cli.py`, `chat.py`, `tui.py`
- **Total Files Reviewed:** 155 (145 Python, 6 YAML configs, `.env`, `.gitignore`, `AGENTS.md`, `README.md`)
- **Total Findings:** CRITICAL: 2 | HIGH: 8 | MEDIUM: 4 | LOW: 0

---

## Systemic Patterns
> Root causes that drive multiple findings below. Read before executing any fix.

- **[PATTERN-01]** `scripts/dead_code_detector.py` was written entirely outside the project's coding standards. It uses `argparse` instead of Click, `import logging` instead of centralized logging, `datetime.now()` instead of `utc_now()`, positional CLI arguments, bare `except:` clauses, `print()` statements, hardcoded values, and an incorrect `sys.path` that points to `scripts/` instead of the project root. This single file drives findings #1–#9 and #12–#13. The fix is a full rewrite to conform to the same standards that `scripts/compliance_checker.py` already follows.

- **[PATTERN-02]** Every unit test file (15 files) uses `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`) to mock internal dependencies. The QA ruleset requires tests to exercise real code against the real platform, targeting public interfaces (black-box). This affects the entire `tests/unit/` tree. Drives finding #11.

---

## Findings

| # | Criticality | File(s) | Line(s) | Rule Violated | Current Behaviour | Expected Behaviour | Pattern Ref |
|---|-------------|---------|---------|---------------|-------------------|-------------------|-------------|
| 1 | CRITICAL | `scripts/dead_code_detector.py` | L439, L490 | Fail fast — no swallowed exceptions | Bare `except:` clauses silently swallow all exceptions, returning `0` or empty list | Catch specific exception types (`SyntaxError`, `OSError`, `UnicodeDecodeError`); log the error; propagate or fail fast | PATTERN-01 |
| 2 | CRITICAL | `scripts/dead_code_detector.py` | L429 | Timezone-naive UTC via `utc_now()` | `datetime.now().isoformat()` produces local-timezone timestamp | `utc_now().isoformat()` from `modules.backend.core.utils` | PATTERN-01 |
| 3 | HIGH | `scripts/dead_code_detector.py` | L24 | Centralized logging only | `import logging` — direct stdlib import | `from modules.backend.core.logging import get_logger` | PATTERN-01 |
| 4 | HIGH | `scripts/dead_code_detector.py` | L35–47 | Centralized logging only | Custom `setup_logging()` function using `logging.basicConfig()` | Use `setup_logging()` from `modules.backend.core.logging` | PATTERN-01 |
| 5 | HIGH | `scripts/dead_code_detector.py` | L64 | Centralized logging only | `self.logger = logging.getLogger(__name__)` — direct logger instantiation | Use `get_logger(__name__)` from centralized logging module | PATTERN-01 |
| 6 | HIGH | `scripts/dead_code_detector.py` | L577–579 | CLI `--options` only, no positional args | `parser.add_argument('path', nargs='?', default='.')` — positional argument | Convert to `--path` option flag: `@click.option("--path", default=".", ...)` | PATTERN-01 |
| 7 | HIGH | `scripts/dead_code_detector.py` | L27, L558 | CLI framework consistency | Uses `argparse.ArgumentParser` | Use `Click` (`@click.command()` with `@click.option()`) consistent with all other scripts | PATTERN-01 |
| 8 | HIGH | `scripts/dead_code_detector.py` | L32 | Project root via `.project_root` | `sys.path.insert(0, str(Path(__file__).parent))` — adds `scripts/` to path, not project root; modules cannot be imported | `sys.path.insert(0, str(Path(__file__).parent.parent))` to add project root, then use `find_project_root()` | PATTERN-01 |
| 9 | HIGH | `scripts/dead_code_detector.py` | L629, L631 | No ad-hoc `print()` | `print()` statements for output | Use `click.echo()` for CLI output | PATTERN-01 |
| 10 | HIGH | `cli.py` | L597, L634 | Project root via `.project_root` | `PROJECT_ROOT = Path(__file__).parent` used for alembic.ini path construction and `cwd` in `run_migrations()` | Use `find_project_root()` from `modules.backend.core.config` for all path construction after bootstrapping | — |
| 11 | HIGH | 15 files in `tests/unit/` | Various | No mocked tests; black-box testing | `from unittest.mock import MagicMock, AsyncMock, patch` in: `test_config.py`, `test_exception_handlers.py`, `test_logging.py`, `test_middleware.py`, `test_pagination.py`, `test_security.py`, `test_health.py`, `test_note_service.py`, `test_base_service.py`, `test_startup_checks.py`, `test_rate_limiter.py`, `test_adapters.py`, `test_middlewares.py`, `test_notifications.py`, `conftest.py` | Tests must exercise real code against the real platform; replace mocks with real implementations or move to integration tests | PATTERN-02 |
| 12 | MEDIUM | `scripts/dead_code_detector.py` | L78–81 | No hardcoded values | `self.preserved_patterns = {'test_', '__main__', ...}` hardcoded in class body | Read from configuration file or accept as CLI option | PATTERN-01 |
| 13 | MEDIUM | `scripts/dead_code_detector.py` | L110–114 | No hardcoded values | Hardcoded directory skip list: `['__pycache__', '.git', '.venv', ...]` in method body | Read from configuration file or accept as CLI option | PATTERN-01 |
| 14 | MEDIUM | `config/settings/application.yaml` | L1–27 | YAML files must have commented list of all options at top | Comment header lists `telegram.webhook_path` and `telegram.authorized_users` but omits `telegram.max_message_length` | Add `#     max_message_length - Maximum message length (integer, default: 4096)` to the comment header | — |
| 15 | MEDIUM | `tests/unit/backend/repositories/` | — | Every public module interface must have tests | Directory exists with empty `__init__.py` but contains no test files; `NoteRepository` and `BaseRepository` have zero dedicated tests | Add test files covering the public interfaces of `BaseRepository` and `NoteRepository` | — |

---

## Execution Order

> Dependency-sequenced. The coding agent must not skip ahead. Some fixes will break others if done out of order.

1. **[PATTERN-01]** — Rewrite `scripts/dead_code_detector.py` to comply with project coding standards. This single action resolves findings #1, #2, #3, #4, #5, #6, #7, #8, #9, #12, #13. Use `scripts/compliance_checker.py` as the reference implementation (it already follows all standards: Click CLI, `--verbose`/`--debug`, centralized logging, no positional args, no hardcoded values). The rewrite must:
   - Replace `argparse` with `Click`
   - Convert positional `path` to `--path` option
   - Replace `import logging` / `logging.getLogger()` / `logging.basicConfig()` with centralized `get_logger()` / `setup_logging()` from `modules.backend.core.logging`
   - Replace `datetime.now()` with `utc_now()` from `modules.backend.core.utils`
   - Replace bare `except:` with specific exception types and proper logging
   - Replace `print()` with `click.echo()`
   - Fix `sys.path.insert` to point to project root (`Path(__file__).parent.parent`)
   - Move hardcoded `preserved_patterns` and directory skip list to CLI options or a config file
   - Add `--verbose` and `--debug` options wired to centralized logging (already has these as argparse flags — just convert to Click)

2. **Finding #10** — In `cli.py`, replace the two uses of `PROJECT_ROOT` after bootstrapping (L597 and L634) with `find_project_root()`. The `PROJECT_ROOT = Path(__file__).parent` assignment at L26 and the `sys.path.insert` at L27 must remain for bootstrapping, but all subsequent path construction must use `find_project_root()`.

3. **Finding #14** — In `config/settings/application.yaml`, add `max_message_length` to the commented option header under the `telegram` section. This is a documentation-only change with no code impact.

4. **Finding #15** — Add test files to `tests/unit/backend/repositories/` covering the public interfaces of `BaseRepository` and `NoteRepository`. These should be implemented without `unittest.mock` per finding #11, or placed in `tests/integration/` if they require a real database.

5. **[PATTERN-02] Finding #11** — Audit all 15 unit test files using `unittest.mock`. For each, determine whether the mocked functionality can be replaced with real execution. Tests that require external infrastructure (database, Redis, Anthropic API) should be moved to `tests/integration/` or `tests/e2e/`. Tests that mock purely for isolation where real code can run should have mocks removed. This is a large-scope refactoring effort and should be done file-by-file after all other findings are resolved.

---

## Out of Scope

> Findings intentionally excluded from this execution run and why.

| # | Criticality | File(s) | Reason Excluded |
|---|-------------|---------|-----------------|
| — | LOW | `modules/backend/core/logging.py` L40 | `import logging` is required — this IS the centralized logging module; it must import stdlib logging to configure it |
| — | LOW | `modules/backend/migrations/env.py` L10 | `from logging.config import fileConfig` is standard Alembic boilerplate required by the framework |
| — | LOW | `cli.py` L26–27, `chat.py` L25–26, `tui.py` L19–20 | `PROJECT_ROOT = Path(__file__).parent` + `sys.path.insert` for bootstrapping is necessary — `find_project_root()` cannot be called before the import path is configured. Only flagged in #10 where `PROJECT_ROOT` is reused after bootstrapping |
| — | LOW | `modules/backend/core/logging.py` L51 | `VALID_SOURCES = frozenset({...})` — this is a validation constant, not a configurable value; it defines the protocol contract for log source fields |
| — | LOW | `cli.py` L32 | `LONG_RUNNING_SERVICES = {"server", ...}` — this is a code-structural constant mapping CLI service names to behaviour, not a configurable value |
| — | INFO | Test fixture files (`test_code_qa.py` L35, `test_compliance.py` L30) | Lines containing `from .sibling import something` and `import logging` are intentional test fixtures written to temp files for compliance scanner testing — not actual code violations |
