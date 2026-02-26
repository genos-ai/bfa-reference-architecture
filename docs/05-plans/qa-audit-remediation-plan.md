# QA Execution Plan

## Run Metadata
- **Date:** 2026-02-26
- **Codebase Root:** `/Users/herman.young/development/bfa_reference_architecture`
- **Entry Points Scanned:** `cli.py`, `chat.py`, `tui.py`
- **Total Files Reviewed:** 146 Python files + 11 config files + 3 other (pytest.ini, requirements.txt, .project_root)
- **Total Findings:** CRITICAL: 1 | HIGH: 9 | MEDIUM: 8 | LOW: 4

---

## Systemic Patterns
> Root causes that drive multiple findings below. Read before executing any fix.

- **[PATTERN-01]** **Decentralized YAML loading for agent configs.** Three files under `modules/backend/agents/coordinator/` each import `yaml` directly and implement their own YAML loading from `config/agents/`, bypassing the centralized `load_yaml_config()` in `core/config.py`. The centralized function only supports `config/settings/`. Agent config dicts are used raw with no Pydantic schema validation (unlike settings YAML which use strict schemas with `extra="forbid"`). Invalid keys, wrong types, or missing fields surface as runtime KeyErrors instead of startup failures. Drives findings #3, #4, #5.

- **[PATTERN-02]** **Pervasive mock-based unit testing.** 15 test files import `unittest.mock`. The unit `conftest.py` provides mock fixtures for database sessions, Redis, settings, app config, HTTP client, and logger. Individual test modules use `MagicMock`, `AsyncMock`, and `patch()` to replace repositories, sessions, and core dependencies. Tests verify mock interaction contracts rather than exercising real code paths against the real platform. Drives findings #11, #12.

- **[PATTERN-03]** **Global mutable singletons without lifecycle management.** 8+ modules use module-level `_variables` as lazy singletons: `database.py` (_engine, _async_session_factory), `bot.py` (_bot, _dispatcher), `gateway/registry.py` (_adapters, _initialized), `rate_limiter.py` (_rate_limiter), `main.py` (_app), `qa/agent.py` (_agent, _conversations), `health/agent.py` (_agent). None have reset mechanisms, thread-safety guarantees, or cleanup hooks. Drives findings #8, #9.

- **[PATTERN-04]** **`scripts/` directory ignores project standards.** `dead_code_detector.py` uses `import logging` (4 instances), `logging.basicConfig()`, `argparse` with a positional argument, `datetime.now()`, bare `except:` clauses, and `os.path` for existence checks. It does not use `.project_root`, centralized config, or centralized logging. Drives finding #20.

- **[PATTERN-05]** **Hardcoded constants in module source.** Several modules define constants or dataclass defaults representing configurable values that should be in YAML. Drives findings #6, #7, #10.

---

## Findings

| # | Criticality | File(s) | Line(s) | Rule Violated | Current Behaviour | Expected Behaviour | Pattern Ref |
|---|-------------|---------|---------|---------------|-------------------|-------------------|-------------|
| 1 | CRITICAL | `modules/backend/gateway/security/startup_checks.py` | L77-L93 | Fail fast / no silent security gaps | `_check_secret_strength()` validates `jwt_secret` and `api_key_salt` lengths but ignores `webhook_secret_min_length` (defined as 16 in `security.yaml`). Current `TELEGRAM_WEBHOOK_SECRET=1234567890` (10 chars) passes startup checks. | `_check_secret_strength()` must also validate `telegram_webhook_secret` against `secrets_validation.webhook_secret_min_length`. Application must refuse to start if any configured minimum is not met. | — |
| 2 | HIGH | `modules/backend/agents/coordinator/coordinator.py` | L54 | No hardcoded dependencies / centralized secrets | `os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)` modifies global process environment at runtime. Bypasses centralized secret management; creates implicit coupling between coordinator and PydanticAI's env-var configuration mechanism. | Pass secrets through a typed configuration object or constructor injection into PydanticAI, not via mutable global env vars. | — |
| 3 | HIGH | `modules/backend/agents/coordinator/middleware.py` | L21-L26 | Centralized config loading / no ad-hoc YAML | `_load_coordinator_config()` loads `config/agents/coordinator.yaml` via raw `yaml.safe_load()` with no schema validation. Invalid or missing keys cause KeyError at runtime. | Extend centralized config system to support agent configs with Pydantic schemas (or add a parallel `load_agent_config()` with validation). | PATTERN-01 |
| 4 | HIGH | `modules/backend/agents/coordinator/middleware.py` | L112 | Fail fast / no silent failures | `guardrails["max_input_length"]` uses direct dict subscript. If `guardrails` section is missing or incomplete in `coordinator.yaml`, raises `KeyError` at request time instead of at startup. | Validate coordinator config structure at load time via Pydantic schema. Access validated typed attributes instead of raw dict subscripts. | PATTERN-01 |
| 5 | HIGH | `modules/backend/agents/coordinator/coordinator.py` | L23, L26 | No dead code | `from functools import lru_cache` (L23) and `import yaml` (L26) are imported but never used in this file. Indicates incomplete refactoring when these functions were moved to `middleware.py` and `registry.py`. | Remove both unused imports. | PATTERN-01 |
| 6 | HIGH | `modules/backend/gateway/adapters/telegram.py` | L16 | No hardcoded values | `TELEGRAM_MAX_MESSAGE_LENGTH = 4096` is a module-level constant. | Move to `config/settings/application.yaml` under `telegram` section (e.g., `max_message_length: 4096`) and read via `get_app_config().application.telegram.max_message_length`. | PATTERN-05 |
| 7 | HIGH | `modules/telegram/middlewares/auth.py` | L19-L23, L117 | No hardcoded values / configurable behaviour | `USER_ROLES = {"admin": 3, "trader": 2, "viewer": 1}` is hardcoded. Role assignment logic (L117: first user in list = admin, rest = traders) is a hardcoded business rule. | Move role definitions and user-to-role mapping to YAML config. Role assignment should be configurable, not positional. | PATTERN-05 |
| 8 | HIGH | `modules/backend/core/database.py`, `modules/telegram/bot.py`, `modules/backend/gateway/registry.py`, `modules/backend/gateway/security/rate_limiter.py`, `modules/backend/main.py`, `modules/backend/agents/vertical/code/qa/agent.py`, `modules/backend/agents/vertical/system/health/agent.py` | various | No global mutable state | 8+ modules use module-level `_variables` as lazy singletons (`_engine`, `_bot`, `_adapters`, `_rate_limiter`, `_app`, `_agent`, etc.). No reset mechanism for testing, no thread safety, no cleanup hooks. | Wrap singletons in a lifecycle-managed container or application context that supports reset (for testing), proper shutdown, and thread-safe initialization. | PATTERN-03 |
| 9 | HIGH | `modules/backend/agents/vertical/code/qa/agent.py` | L~139 | No global mutable state / resource management | `_conversations: dict[str, list] = {}` accumulates conversation histories in memory with no cleanup, TTL, or size limit. Unbounded growth in a long-running server process. | Use Redis-backed session storage (TTL from `coordinator.yaml` `redis_ttl.session: 3600`), or at minimum add an LRU eviction policy. | PATTERN-03 |
| 10 | HIGH | `modules/backend/agents/deps/base.py` | L77 | No hardcoded values | `max_delegation_depth: int = 2` is a hardcoded default on the `HorizontalAgentDeps` dataclass. | Read from `coordinator.yaml` `routing.max_routing_depth` at construction time. Remove hardcoded default. | PATTERN-05 |
| 11 | MEDIUM | `tests/unit/conftest.py`, `tests/unit/backend/services/test_note_service.py`, `tests/unit/backend/core/test_middleware.py`, `tests/unit/backend/core/test_security.py`, `tests/unit/backend/core/test_exception_handlers.py`, `tests/unit/backend/core/test_pagination.py`, `tests/unit/backend/core/test_logging.py`, `tests/unit/backend/api/test_health.py`, `tests/unit/backend/services/test_base_service.py`, `tests/unit/telegram/test_middlewares.py`, `tests/unit/telegram/test_notifications.py`, `tests/unit/backend/gateway/test_startup_checks.py`, `tests/unit/backend/gateway/test_rate_limiter.py`, `tests/unit/backend/gateway/test_adapters.py` | various | No mocked tests / tests must exercise real code | 15 test files import `unittest.mock`. Unit `conftest.py` provides `mock_db_session`, `mock_redis`, `mock_settings`, `mock_app_config`, `mock_logger`. Individual tests use `MagicMock`, `AsyncMock`, `patch()` to replace all dependencies. | Rewrite tests to exercise real code against real infrastructure (in-memory SQLite, real config loading, real service instantiation). Mocks should be the exception, not the default. | PATTERN-02 |
| 12 | MEDIUM | `tests/conftest.py` | L63 | No os.getenv with hardcoded fallback | `os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")` uses a hardcoded fallback default. | Read from a test configuration YAML or fail fast if the env var is not set. Alternatively, define the default in a `config/settings/test.yaml`. | PATTERN-02 |
| 13 | MEDIUM | `AGENTS.md`, `modules/__init__.py` | L1-L6 (modules/__init__.py) | No dead references / documentation accuracy | `AGENTS.md` key modules table lists `modules/frontend/ \| React + Vite + Tailwind`. `modules/__init__.py` docstring references `frontend/: Web frontend`. The directory does not exist. | Remove the `modules/frontend/` reference from `AGENTS.md` and `modules/__init__.py`, or create the module if planned. Documentation must match reality. | — |
| 14 | MEDIUM | `cli.py` | — | File size target ~500 lines | `cli.py` is 706 lines. Contains 10+ service handler functions (run_server, run_worker, run_scheduler, run_telegram_poll, check_health, show_config, run_tests, run_migrations, show_info, plus helpers). | Extract service handlers into a `modules/backend/cli/` subpackage (e.g., `services.py`, `migrations.py`, `health.py`). Keep `cli.py` as a thin dispatcher. | — |
| 15 | MEDIUM | `modules/backend/agents/coordinator/coordinator.py`, `modules/backend/agents/coordinator/registry.py`, `modules/backend/agents/coordinator/router.py`, `modules/backend/agents/coordinator/middleware.py` | — | Every public interface must have tests | The coordinator module (322 lines), registry, router, and middleware have zero test coverage. The coordinator is the central orchestration module for all agent interactions. | Create `tests/unit/backend/agents/test_coordinator.py`, `test_registry.py`, `test_router.py`, `test_middleware.py` covering routing, direct invocation, guardrails, cost tracking, and registry loading. | — |
| 16 | MEDIUM | `modules/backend/repositories/base.py`, `modules/backend/repositories/note.py` | — | Every public interface must have tests | `tests/unit/backend/repositories/__init__.py` exists but the directory contains no test files. `BaseRepository` (11 public methods) and `NoteRepository` (6 additional methods) have no dedicated tests. | Create `tests/unit/backend/repositories/test_base_repository.py` and `test_note_repository.py` testing CRUD operations against the in-memory SQLite test database. | — |
| 17 | MEDIUM | `tests/e2e/`, `tests/integration/backend/workflows/` | — | No empty scaffolding | `tests/e2e/` contains only `__init__.py` and `conftest.py` with zero test files. `tests/integration/backend/workflows/` contains only `__init__.py`. | Either add tests or remove the empty directories to avoid misleading structure. | — |
| 18 | MEDIUM | `modules/backend/agents/coordinator/registry.py` | L68-L82 | Fail fast / no silent failures | `_ensure_loaded()` silently skips any agent YAML that is missing `agent_name` or has `enabled: false`. No warning is logged for malformed configs (e.g., missing `agent_name` key). Only successfully loaded agents are counted. | Log a warning for each skipped agent YAML file, distinguishing between "disabled by config" and "malformed config". Fail fast on YAML parse errors. | PATTERN-01 |
| 19 | LOW | `requirements.txt` | — | No unused dependencies | `typer>=0.9.0` is listed but never imported anywhere in the codebase. CLI uses `click` exclusively. | Remove `typer>=0.9.0` from `requirements.txt`. | — |
| 20 | LOW | `scripts/dead_code_detector.py` | L24, L29, L47, L64, L429, L439, L490, L577-L578, L608 | Multiple: centralized logging, no datetime.now, CLI options, fail fast | Uses `import logging` (L24), `logging.basicConfig()` (L47), `logging.getLogger()` (L64, L608), `datetime.now()` (L429), bare `except:` (L439, L490), `argparse` with positional argument `path` (L577-L578). | Rewrite to use `click` with `--options` only, centralized `setup_logging()` / `get_logger()`, `utc_now()`, and proper exception handling. Remove bare `except:` clauses. | PATTERN-04 |
| 21 | LOW | `modules/telegram/middlewares/auth.py` | L117 | Configurable behaviour | `if user_id == authorized_users[0]: role = "admin"` — role is determined by list position. No explicit user-to-role mapping. | Add a configurable role mapping in `application.yaml` (e.g., `telegram.user_roles: {123456789: admin, 987654321: trader}`). | PATTERN-05 |
| 22 | LOW | `tests/conftest.py` | L95-L96, L104-L105 | No hardcoded values in code | `echo=False` (L95-96), `pool_size=5` (L104), `max_overflow=10` (L105) are hardcoded in the test database engine creation. | Read from a test configuration section or centralize test database settings. | — |

---

## Execution Order

> Dependency-sequenced. The coding agent must not skip ahead. Some fixes will break others if done out of order.

1. **Finding #1** (CRITICAL) — Fix startup security check to enforce `webhook_secret_min_length`. This is a security gap with zero dependencies. Fix and verify independently. Update `TELEGRAM_WEBHOOK_SECRET` in `config/.env` to meet the 16-char minimum.

2. **[PATTERN-01]** — Centralize agent config loading. Create Pydantic schemas for `coordinator.yaml` and `agent.yaml` structures. Extend `core/config.py` with a `load_agent_config()` function. Unblocks findings #3, #4, #5, #18.

3. **Finding #3** — Replace raw `yaml.safe_load()` in `middleware.py` with validated config loading from step 2.

4. **Finding #4** — After #3, the guardrails config is now validated at load time. Direct dict subscript is replaced by typed attribute access.

5. **Finding #5** — Remove unused `import yaml` and `from functools import lru_cache` from `coordinator.py`. Safe after #3 confirms no usage.

6. **Finding #18** — After #2, add warning logs in registry for skipped/malformed agent configs.

7. **Finding #2** — Refactor API key injection in `coordinator.py`. Pass secrets via deps or model constructor instead of `os.environ.setdefault`. Must test that PydanticAI agents still receive the key correctly.

8. **[PATTERN-05]** — Move hardcoded constants to YAML config. Unblocks findings #6, #7, #10, #21.

9. **Finding #6** — Move `TELEGRAM_MAX_MESSAGE_LENGTH` to `application.yaml`. Update `TelegramAdapter` and `config_schema.py`.

10. **Finding #7** — Move `USER_ROLES` to config. Add configurable user-to-role mapping.

11. **Finding #10** — Remove hardcoded `max_delegation_depth` default. Read from coordinator config.

12. **Finding #21** — Add configurable role mapping in `application.yaml`. Depends on #10 for config pattern.

13. **Finding #13** — Remove `modules/frontend/` references from `AGENTS.md` and `modules/__init__.py`. No code dependency.

14. **Finding #14** — Split `cli.py` into submodules. Extract handler functions into `modules/backend/cli/`. Keep `cli.py` as thin dispatcher.

15. **Finding #19** — Remove `typer>=0.9.0` from `requirements.txt`.

16. **[PATTERN-03]** — Address global mutable state. This is a large refactoring effort. Unblocks findings #8, #9.

17. **Finding #8** — Introduce an application context or container for singletons. Add reset hooks for testing.

18. **Finding #9** — Replace `_conversations` dict with Redis-backed storage using configured TTL, or add LRU eviction. Depends on #17 for singleton lifecycle pattern.

19. **[PATTERN-02]** — Rewrite mock-heavy tests. This is the highest effort item. Unblocks findings #11, #12.

20. **Finding #12** — Replace `os.environ.get` with test config loading.

21. **Finding #11** — Systematically replace mock-based tests with integration-style tests using real services and in-memory SQLite.

22. **Finding #15** — Write tests for coordinator, registry, router, middleware. Should use the new test patterns from step 21.

23. **Finding #16** — Write tests for BaseRepository and NoteRepository against in-memory SQLite.

24. **Finding #17** — Either add e2e and workflow tests or remove empty directories.

25. **Finding #22** — Centralize test DB connection params.

26. **Finding #20** — Rewrite `dead_code_detector.py` to use project standards (click, centralized logging, utc_now, proper error handling). Lowest priority — can be done independently.

---

## Out of Scope

> Findings intentionally excluded from this execution run and why.

| # | Criticality | File(s) | Reason Excluded |
|---|-------------|---------|-----------------|
| — | LOW | `scripts/compliance_checker.py` | Already follows project standards (click, --verbose/--debug, centralized logging). No violations found. |
| — | INFO | `config/.env` | Contains development credentials (Telegram bot token, Anthropic API key). These are expected in a dev `.env` file. File appears to be `.gitignored` (not shown as tracked in `git status`). Not a code violation. |
| — | INFO | `modules/backend/tasks/` | `broker.py`, `example.py`, `scheduled.py`, `scheduler.py` reviewed. No violations found against the ruleset. |
| — | INFO | `modules/backend/migrations/env.py` | Alembic-generated file. Follows Alembic conventions, not project conventions. |
| — | INFO | `__pycache__/` in project root | Appears in filesystem but is expected to be `.gitignored`. Not a code quality issue. |
