# Implementation Plan: Agent System Rebuild (Doc 47)

*Created: 2026-02-26*
*Status: Not Started*
*Reference: [47-agent-module-organization.md](../99-reference-architecture/47-agent-module-organization.md)*

---

## Summary

Rebuild the agent system from scratch following doc 47 conventions. Extract scanning logic into `ComplianceScannerService`, create shared tool implementations as pure functions, build the coordinator with typed models and middleware, rebuild QA and health agents as thin wrappers (~80-120 lines each), set up the layered prompt system, and add proper tests with `TestModel` and `ALLOW_MODEL_REQUESTS = False` CI guardrails.

**Approach**: Build bottom-up — foundation (deps, service, tools) first, then infrastructure (coordinator), then agents on top. Follow the refactoring protocol: commit, branch, backup, build, test, clean up.

**Public interface is preserved**: `handle()`, `handle_direct()`, `handle_direct_stream()`, `list_agents()` keep the same signatures. `chat.py`, `tui.py`, REST endpoints, and the compliance checker script continue to work without changes to their calling code.

---

## Progress Tracker

### Phase 0: Git Safety

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 0.1 | Commit current working state on `main` | All | Not Started |
| 0.2 | Create branch `feature/agent-system-rebuild` | — | Not Started |
| 0.3 | Back up QA agent | `modules/backend/agents/vertical/code/qa/agent.py` → `.bak` | Not Started |
| 0.4 | Back up health agent | `modules/backend/agents/vertical/system/health/agent.py` → `.bak` | Not Started |
| 0.5 | Back up coordinator | `modules/backend/agents/coordinator/coordinator.py` → `.bak` | Not Started |

### Phase 1: Foundation — Deps and Schemas

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 1.1 | Create `agents/deps/__init__.py` (minimal exports) | `modules/backend/agents/deps/__init__.py` | Not Started |
| 1.2 | Create `FileScope` dataclass with `check_read()`, `check_write()`, `is_readable()`, `_matches()` | `modules/backend/agents/deps/base.py` | Not Started |
| 1.3 | Create `BaseAgentDeps` dataclass (project_root, scope, config) | `modules/backend/agents/deps/base.py` | Not Started |
| 1.4 | Create `QaAgentDeps(BaseAgentDeps)` with `on_progress` callback and `emit()` method | `modules/backend/agents/deps/base.py` | Not Started |
| 1.5 | Create `HealthAgentDeps(BaseAgentDeps)` with `app_config` field | `modules/backend/agents/deps/base.py` | Not Started |
| 1.6 | Create `HorizontalAgentDeps(BaseAgentDeps)` with `allowed_agents`, `max_delegation_depth`, `coordinator` | `modules/backend/agents/deps/base.py` | Not Started |
| 1.7 | Move `Violation` and `QaAuditResult` from old QA agent to shared schemas | `modules/backend/agents/schemas.py` | Not Started |
| 1.8 | Move `HealthCheckResult` from old health agent to shared schemas | `modules/backend/agents/schemas.py` | Not Started |

### Phase 2: ComplianceScannerService

Extract all scanning logic from the old QA agent (`.bak` file) into a proper service.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 2.1 | Create `ComplianceScannerService` class with `__init__(self, project_root, config)` | `modules/backend/services/compliance.py` | Not Started |
| 2.2 | Extract `_load_agent_config()` → `load_config()` (module-level function) | `modules/backend/services/compliance.py` | Not Started |
| 2.3 | Extract `_get_exclusion_paths()` → `get_exclusion_paths()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.4 | Extract `_is_excluded()` → `is_excluded()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.5 | Extract `_get_enabled_rule_ids()` → `get_enabled_rule_ids()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.6 | Extract `_get_rule_severity()` → `get_rule_severity()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.7 | Extract `_collect_python_files()` → `collect_python_files()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.8 | Extract `_scan_file_lines()` → `scan_file_lines()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.9 | Extract body of `scan_import_violations` tool → `scan_import_violations()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.10 | Extract body of `scan_datetime_violations` tool → `scan_datetime_violations()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.11 | Extract body of `scan_hardcoded_values` tool → `scan_hardcoded_values()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.12 | Extract body of `scan_file_sizes` tool → `scan_file_sizes()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.13 | Extract body of `scan_cli_options` tool → `scan_cli_options()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.14 | Extract body of `scan_config_files` tool → `scan_config_files()` method | `modules/backend/services/compliance.py` | Not Started |
| 2.15 | Update `scripts/compliance_checker.py` to import from `ComplianceScannerService` instead of old QA agent private functions | `scripts/compliance_checker.py` | Not Started |

### Phase 3: Shared Tool Implementations

Pure async functions in `agents/tools/`. No PydanticAI dependency. Each accepts explicit parameters (project_root, scope, config). Scope is enforced as the first operation in every function that does file I/O.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 3.1 | Create `agents/tools/__init__.py` (minimal) | `modules/backend/agents/tools/__init__.py` | Not Started |
| 3.2 | Create `filesystem.read_file(project_root, file_path, scope)` — scope check, read file, return with line numbers | `modules/backend/agents/tools/filesystem.py` | Not Started |
| 3.3 | Create `filesystem.list_files(project_root, scope, exclusions)` — scope check, walk project, return relative paths | `modules/backend/agents/tools/filesystem.py` | Not Started |
| 3.4 | Create `compliance.scan_imports(project_root, scope, config)` — calls `ComplianceScannerService.scan_import_violations()` | `modules/backend/agents/tools/compliance.py` | Not Started |
| 3.5 | Create `compliance.scan_datetime(project_root, scope, config)` — calls service | `modules/backend/agents/tools/compliance.py` | Not Started |
| 3.6 | Create `compliance.scan_hardcoded(project_root, scope, config)` — calls service | `modules/backend/agents/tools/compliance.py` | Not Started |
| 3.7 | Create `compliance.scan_file_sizes(project_root, scope, config)` — calls service | `modules/backend/agents/tools/compliance.py` | Not Started |
| 3.8 | Create `compliance.scan_cli_options(project_root, scope, config)` — calls service | `modules/backend/agents/tools/compliance.py` | Not Started |
| 3.9 | Create `compliance.scan_config_files(project_root, scope, config)` — calls service | `modules/backend/agents/tools/compliance.py` | Not Started |
| 3.10 | Create `code.apply_fix(project_root, file_path, old_text, new_text, scope)` — scope check, exact text replacement, return success/error dict | `modules/backend/agents/tools/code.py` | Not Started |
| 3.11 | Create `code.run_tests(project_root)` — runs `pytest tests/unit -v --tb=short`, returns pass/fail dict with tail output | `modules/backend/agents/tools/code.py` | Not Started |
| 3.12 | Create `system.check_system_health()` — calls `check_database()` and `check_redis()` from health module, returns component status dict | `modules/backend/agents/tools/system.py` | Not Started |
| 3.13 | Create `system.get_app_info(app_config)` — extracts name, version, environment, debug from app_config | `modules/backend/agents/tools/system.py` | Not Started |

### Phase 4: Prompt Files

Create the three-layer prompt hierarchy in `config/prompts/`.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 4.1 | Create `organization/principles.md` — mission, values, priorities (reliability, security, transparency, human authority, cost awareness) | `config/prompts/organization/principles.md` | Not Started |
| 4.2 | Create `organization/coding_standards.md` — universal coding rules from doc 08 (absolute imports, centralized logging, utc_now, no hardcoding, file size limits) | `config/prompts/organization/coding_standards.md` | Not Started |
| 4.3 | Create `categories/system.md` — system agent standards (prioritize stability, log before acting, verify before modifying) | `config/prompts/categories/system.md` | Not Started |
| 4.4 | Create `categories/code.md` — code agent standards (follow doc 08, run tests after changes, be precise with file paths and line numbers) | `config/prompts/categories/code.md` | Not Started |
| 4.5 | Create `agents/system/health/system.md` — extracted from old `SYSTEM_PROMPT` in health agent (diagnostic agent, check services, actionable advice) | `config/prompts/agents/system/health/system.md` | Not Started |
| 4.6 | Create `agents/code/qa/system.md` — extracted from old `SYSTEM_PROMPT` in QA agent (compliance workflow, fix auto-fixable, escalate design decisions, run tests) | `config/prompts/agents/code/qa/system.md` | Not Started |

### Phase 5: Coordinator

Rebuild the coordinator with typed models, proper registry, routing, and middleware.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 5.1 | Create `CoordinatorRequest` (user_input, agent, conversation_id, channel, session_type, tool_access_level) and `CoordinatorResponse` (agent_name, output, metadata) | `modules/backend/agents/coordinator/models.py` | Not Started |
| 5.2 | Create `AgentRegistry` class — walks `config/agents/**/agent.yaml`, caches with `@lru_cache`, provides `get()`, `has()`, `list_all()`, `get_by_keyword()` | `modules/backend/agents/coordinator/registry.py` | Not Started |
| 5.3 | Create `RuleBasedRouter` class — `route(request) -> str or None`, keyword matching against registry capabilities | `modules/backend/agents/coordinator/router.py` | Not Started |
| 5.4 | Create `with_guardrails(func)` decorator — checks input length and injection patterns from coordinator.yaml | `modules/backend/agents/coordinator/middleware.py` | Not Started |
| 5.5 | Create `with_cost_tracking(func)` decorator — logs tokens, cost, duration via structlog | `modules/backend/agents/coordinator/middleware.py` | Not Started |
| 5.6 | Create `assemble_instructions(category, name)` — reads and concatenates prompt layers 0+1+2 from `config/prompts/` | `modules/backend/agents/coordinator/coordinator.py` | Not Started |
| 5.7 | Create `_build_deps(agent_config, project_root)` — constructs FileScope from YAML scope config, returns appropriate deps dataclass | `modules/backend/agents/coordinator/coordinator.py` | Not Started |
| 5.8 | Create `_register_executors()` — discovers agents from registry, imports their run functions, wraps with middleware chain | `modules/backend/agents/coordinator/coordinator.py` | Not Started |
| 5.9 | Rewrite `list_agents()` — uses AgentRegistry instead of raw YAML loading | `modules/backend/agents/coordinator/coordinator.py` | Not Started |
| 5.10 | Rewrite `_route(user_input)` — uses RuleBasedRouter | `modules/backend/agents/coordinator/coordinator.py` | Not Started |
| 5.11 | Rewrite `_execute(agent_name, user_input)` — uses registered executors with middleware | `modules/backend/agents/coordinator/coordinator.py` | Not Started |
| 5.12 | Rewrite `handle(user_input)` — same signature, uses new router and executor | `modules/backend/agents/coordinator/coordinator.py` | Not Started |
| 5.13 | Rewrite `handle_direct(agent_name, user_input)` — same signature, uses new registry and executor | `modules/backend/agents/coordinator/coordinator.py` | Not Started |
| 5.14 | Rewrite `handle_direct_stream(agent_name, user_input, conversation_id)` — same signature, uses new registry, no hardcoded agent name checks | `modules/backend/agents/coordinator/coordinator.py` | Not Started |

### Phase 6: Agents (Thin Wrappers)

Rebuild both agents as thin files. Each agent imports shared tool implementations and registers thin `@agent.tool` wrappers that pass scope from deps.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 6.1 | Rewrite QA agent: module-level `_agent` variable, lazy `_get_agent()` | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.2 | QA agent: use `assemble_instructions("code", "qa")` for instructions | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.3 | QA agent: register `list_python_files` tool wrapper (calls `filesystem.list_files`) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.4 | QA agent: register `scan_import_violations` tool wrapper (calls `compliance.scan_imports`) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.5 | QA agent: register `scan_datetime_violations` tool wrapper (calls `compliance.scan_datetime`) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.6 | QA agent: register `scan_hardcoded_values` tool wrapper (calls `compliance.scan_hardcoded`) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.7 | QA agent: register `scan_file_sizes` tool wrapper (calls `compliance.scan_file_sizes`) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.8 | QA agent: register `scan_cli_options` tool wrapper (calls `compliance.scan_cli_options`) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.9 | QA agent: register `scan_config_files` tool wrapper (calls `compliance.scan_config_files`) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.10 | QA agent: register `read_source_file` tool wrapper (calls `filesystem.read_file`) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.11 | QA agent: register `apply_fix` tool wrapper (calls `code.apply_fix`) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.12 | QA agent: register `run_tests` tool wrapper (calls `code.run_tests`) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.13 | QA agent: implement `run_qa_agent(user_message)` — same signature as before | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.14 | QA agent: implement `run_qa_agent_stream(user_message, conversation_id)` — same signature as before | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.15 | Verify QA agent file is under 120 lines | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 6.16 | Rewrite health agent: module-level `_agent`, lazy `_get_agent()`, `assemble_instructions("system", "health")` | `modules/backend/agents/vertical/system/health/agent.py` | Not Started |
| 6.17 | Health agent: register `check_system_health` tool wrapper (calls `system.check_system_health`) | `modules/backend/agents/vertical/system/health/agent.py` | Not Started |
| 6.18 | Health agent: register `get_app_info` tool wrapper (calls `system.get_app_info`) | `modules/backend/agents/vertical/system/health/agent.py` | Not Started |
| 6.19 | Health agent: implement `run_health_agent(user_message)` — same signature as before | `modules/backend/agents/vertical/system/health/agent.py` | Not Started |
| 6.20 | Verify health agent file is under 80 lines | `modules/backend/agents/vertical/system/health/agent.py` | Not Started |

### Phase 7: Configuration Updates

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 7.1 | Update QA agent YAML: add `agent_type: vertical`, add `scope.read` and `scope.write` paths, change `tools` list to dotted names | `config/agents/code/qa/agent.yaml` | Not Started |
| 7.2 | Update health agent YAML: add `agent_type: vertical`, add `scope` section, add `tools` list with dotted names | `config/agents/system/health/agent.yaml` | Not Started |
| 7.3 | Create coordinator YAML: `routing` (strategy, fallback_agent), `limits` (max_requests, max_tokens, max_cost, timeouts), `guardrails` (max_input_length, injection_patterns) | `config/agents/coordinator.yaml` | Not Started |

### Phase 8: API Wiring

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.1 | Update agent endpoint imports to use new coordinator module (import paths only — public interface unchanged) | `modules/backend/api/v1/endpoints/agents.py` | Not Started |
| 8.2 | Verify `chat.py` works without changes (calls `handle_direct`/`handle` via coordinator) | `chat.py` | Not Started |
| 8.3 | Verify `tui.py` works without changes (calls coordinator via API) | `tui.py` | Not Started |

### Phase 9: Tests

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 9.1 | Add `ALLOW_MODEL_REQUESTS = False` CI guardrail to test conftest | `tests/conftest.py` | Not Started |
| 9.2 | Create `ComplianceScannerService` unit tests — reuse `project_with_violations` fixture from old tests, test each scanner method | `tests/unit/backend/services/test_compliance.py` | Not Started |
| 9.3 | Test `scan_import_violations` finds relative imports, direct logging, os.getenv fallbacks | `tests/unit/backend/services/test_compliance.py` | Not Started |
| 9.4 | Test `scan_datetime_violations` finds datetime.now() and datetime.utcnow() | `tests/unit/backend/services/test_compliance.py` | Not Started |
| 9.5 | Test `scan_hardcoded_values` finds UPPER_CASE constants, skips dunders | `tests/unit/backend/services/test_compliance.py` | Not Started |
| 9.6 | Test `scan_file_sizes` flags files over limit | `tests/unit/backend/services/test_compliance.py` | Not Started |
| 9.7 | Test `collect_python_files` respects exclusions | `tests/unit/backend/services/test_compliance.py` | Not Started |
| 9.8 | Create `FileScope` unit tests — `check_read` allows/denies, `check_write` allows/denies, `is_readable` returns bool, `_matches` handles wildcards | `tests/unit/backend/agents/test_deps.py` | Not Started |
| 9.9 | Create filesystem tool tests — `read_file` returns content for allowed path, raises `PermissionError` for denied path | `tests/unit/backend/agents/tools/test_filesystem.py` | Not Started |
| 9.10 | Create compliance tool tests — verify tool functions call service and pass through scope | `tests/unit/backend/agents/tools/test_compliance_tools.py` | Not Started |
| 9.11 | Create code tool tests — `apply_fix` replaces text within scope, rejects out-of-scope writes, `run_tests` returns pass/fail dict | `tests/unit/backend/agents/tools/test_code.py` | Not Started |
| 9.12 | Update existing `test_code_qa.py` — change imports to new locations (schemas from `agents/schemas`, service from `services/compliance`), update test class references | `tests/unit/backend/agents/test_code_qa.py` | Not Started |
| 9.13 | Add TestModel agent test for QA agent — verify `run_qa_agent` returns `QaAuditResult` schema | `tests/unit/backend/agents/test_code_qa.py` | Not Started |
| 9.14 | Add TestModel agent test for health agent — verify `run_health_agent` returns `HealthCheckResult` schema | `tests/unit/backend/agents/test_system_health.py` | Not Started |
| 9.15 | Create AgentRegistry unit test — verify it discovers agents from config, `get()` returns config, `has()` works, `list_all()` returns all | `tests/unit/backend/agents/test_registry.py` | Not Started |
| 9.16 | Create RuleBasedRouter unit test — verify keyword matching routes correctly, returns None for no match | `tests/unit/backend/agents/test_router.py` | Not Started |
| 9.17 | Run full unit test suite: `python -m pytest tests/unit -v` | All test files | Not Started |

### Phase 10: Cleanup and Verification

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 10.1 | Remove `agent.py.bak` backup files | 3 `.bak` files | Not Started |
| 10.2 | Verify `scripts/compliance_checker.py` works: `python scripts/compliance_checker.py --verbose` | `scripts/compliance_checker.py` | Not Started |
| 10.3 | Verify `python cli.py --service health --debug` works | `cli.py` | Not Started |
| 10.4 | Verify no dead imports in any modified `__init__.py` files | All `__init__.py` | Not Started |
| 10.5 | Verify QA agent file line count (target: under 120 lines) | `modules/backend/agents/vertical/code/qa/agent.py` | Not Started |
| 10.6 | Verify health agent file line count (target: under 80 lines) | `modules/backend/agents/vertical/system/health/agent.py` | Not Started |
| 10.7 | Verify ComplianceScannerService file line count (target: under 400 lines) | `modules/backend/services/compliance.py` | Not Started |
| 10.8 | Run full test suite one final time: `python -m pytest tests/ -v` | All tests | Not Started |
| 10.9 | Verify no linter errors in new/modified files | All new/modified files | Not Started |

---

## File Inventory

### New Files (23)

| # | File | Purpose |
|---|------|---------|
| 1 | `modules/backend/agents/deps/__init__.py` | Deps package init |
| 2 | `modules/backend/agents/deps/base.py` | BaseAgentDeps, FileScope, agent-specific deps |
| 3 | `modules/backend/agents/schemas.py` | Shared output schemas (Violation, QaAuditResult, HealthCheckResult) |
| 4 | `modules/backend/services/compliance.py` | ComplianceScannerService — all scanning business logic |
| 5 | `modules/backend/agents/tools/__init__.py` | Tools package init |
| 6 | `modules/backend/agents/tools/filesystem.py` | read_file, list_files — pure functions with scope |
| 7 | `modules/backend/agents/tools/compliance.py` | scan_* — thin wrappers calling ComplianceScannerService |
| 8 | `modules/backend/agents/tools/code.py` | apply_fix, run_tests — pure functions with scope |
| 9 | `modules/backend/agents/tools/system.py` | check_system_health, get_app_info — pure functions |
| 10 | `config/prompts/organization/principles.md` | Organization-wide values and priorities |
| 11 | `config/prompts/organization/coding_standards.md` | Universal coding rules from doc 08 |
| 12 | `config/prompts/categories/system.md` | System agent category standards |
| 13 | `config/prompts/categories/code.md` | Code agent category standards |
| 14 | `config/prompts/agents/system/health/system.md` | Health agent identity and instructions |
| 15 | `config/prompts/agents/code/qa/system.md` | QA agent identity, workflow, and rules |
| 16 | `modules/backend/agents/coordinator/models.py` | CoordinatorRequest, CoordinatorResponse |
| 17 | `modules/backend/agents/coordinator/registry.py` | AgentRegistry class |
| 18 | `modules/backend/agents/coordinator/router.py` | RuleBasedRouter class |
| 19 | `modules/backend/agents/coordinator/middleware.py` | with_guardrails, with_cost_tracking decorators |
| 20 | `config/agents/coordinator.yaml` | Coordinator config (routing, limits, guardrails) |
| 21 | `tests/unit/backend/services/test_compliance.py` | ComplianceScannerService tests |
| 22 | `tests/unit/backend/agents/test_deps.py` | FileScope tests |
| 23 | `tests/unit/backend/agents/tools/test_filesystem.py` | Filesystem tool tests |

### Modified Files (8)

| # | File | Change |
|---|------|--------|
| 1 | `modules/backend/agents/coordinator/coordinator.py` | Full rewrite — new registry, router, middleware, prompt assembly |
| 2 | `modules/backend/agents/vertical/code/qa/agent.py` | Full rewrite — thin wrapper, ~120 lines |
| 3 | `modules/backend/agents/vertical/system/health/agent.py` | Full rewrite — thin wrapper, ~80 lines |
| 4 | `config/agents/code/qa/agent.yaml` | Add agent_type, scope, dotted tool names |
| 5 | `config/agents/system/health/agent.yaml` | Add agent_type, scope, dotted tool names |
| 6 | `scripts/compliance_checker.py` | Update imports to ComplianceScannerService |
| 7 | `tests/conftest.py` | Add ALLOW_MODEL_REQUESTS = False |
| 8 | `tests/unit/backend/agents/test_code_qa.py` | Update imports, add TestModel test |

### Backed Up Files (3)

| # | Original | Backup |
|---|----------|--------|
| 1 | `modules/backend/agents/vertical/code/qa/agent.py` | `agent.py.bak` |
| 2 | `modules/backend/agents/vertical/system/health/agent.py` | `agent.py.bak` |
| 3 | `modules/backend/agents/coordinator/coordinator.py` | `coordinator.py.bak` |

---

## Architecture After Completion

```
modules/backend/
├── agents/
│   ├── coordinator/
│   │   ├── coordinator.py      # handle(), assemble_instructions(), _execute()
│   │   ├── models.py           # CoordinatorRequest, CoordinatorResponse
│   │   ├── registry.py         # AgentRegistry (discovers from YAML)
│   │   ├── router.py           # RuleBasedRouter (keyword matching)
│   │   └── middleware.py       # with_guardrails, with_cost_tracking
│   ├── vertical/
│   │   ├── system/health/
│   │   │   └── agent.py        # ~80 lines, thin tool wrappers
│   │   └── code/qa/
│   │       └── agent.py        # ~120 lines, thin tool wrappers
│   ├── tools/
│   │   ├── filesystem.py       # read_file, list_files (pure, scoped)
│   │   ├── compliance.py       # scan_* (delegates to service)
│   │   ├── code.py             # apply_fix, run_tests (pure, scoped)
│   │   └── system.py           # check_health, get_app_info (pure)
│   ├── deps/
│   │   └── base.py             # BaseAgentDeps, FileScope, agent-specific deps
│   └── schemas.py              # Violation, QaAuditResult, HealthCheckResult
├── services/
│   ├── compliance.py           # ComplianceScannerService (all scanning logic)
│   └── ...                     # Existing services unchanged
config/
├── agents/
│   ├── coordinator.yaml        # Routing, limits, guardrails
│   ├── code/qa/agent.yaml      # Updated with scope + dotted tools
│   └── system/health/agent.yaml # Updated with scope + dotted tools
└── prompts/
    ├── organization/           # Layer 0: all agents
    │   ├── principles.md
    │   └── coding_standards.md
    ├── categories/             # Layer 1: per-category
    │   ├── system.md
    │   └── code.md
    └── agents/                 # Layer 2: per-agent
        ├── system/health/system.md
        └── code/qa/system.md
```

---

## Call Chain After Completion

```
User request → Coordinator
  1. AgentRegistry.get_by_keyword() → finds agent name
  2. RuleBasedRouter.route() → confirms routing
  3. assemble_instructions(category, name) → Layer 0 + 1 + 2 prompt
  4. _build_deps(config) → FileScope + BaseAgentDeps
  5. with_guardrails(with_cost_tracking(run_agent))() → middleware chain
  6. agent.run(message, deps=deps, usage_limits=limits) → PydanticAI
  7. @agent.tool wrapper (2 lines) → shared tool implementation
  8. Tool implementation → scope.check_read() → service method
  9. Result flows back → Coordinator → Caller
```

---

## Success Criteria

- [ ] All existing unit tests pass (`python -m pytest tests/unit -v`)
- [ ] `scripts/compliance_checker.py --verbose` works with new service imports
- [ ] `python cli.py --service health --debug` works
- [ ] QA agent file is under 120 lines
- [ ] Health agent file is under 80 lines
- [ ] ComplianceScannerService is under 400 lines
- [ ] No tool implementation contains `RunContext` or any PydanticAI import
- [ ] No agent `agent.py` contains scanning/business logic (only thin wrappers)
- [ ] `ALLOW_MODEL_REQUESTS = False` is set in `tests/conftest.py`
- [ ] All prompts load from `config/prompts/` (no hardcoded `SYSTEM_PROMPT` in agent files)
- [ ] FileScope enforces read/write boundaries in tool implementations
- [ ] Coordinator uses typed `CoordinatorRequest`/`CoordinatorResponse` models
- [ ] No linter errors in new or modified files

---

## Rollback Plan

If the rebuild fails at any phase:

1. `git stash` any uncommitted work
2. `git checkout main` to return to the pre-rebuild state
3. All original functionality is preserved on `main`

The `.bak` files also provide direct line-by-line comparison during development.
