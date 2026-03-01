# Implementation Plan: Agent System Rebuild (Doc 47)

*Created: 2026-02-26*
*Status: Complete*
*Branch: `feature/agent-system-rebuild` (9 commits, 416 tests passing)*
*Reference: [47-agent-module-organization.md](../99-reference-architecture/47-agent-module-organization.md)*

---

## Summary

Rebuilt the agent system from scratch following doc 47 conventions. Extracted scanning logic into `ComplianceScannerService`, created shared tool implementations as pure functions, built the coordinator with typed models and middleware, rebuilt QA and health agents as thin wrappers, set up the layered prompt system, and added proper tests with `TestModel` and `ALLOW_MODEL_REQUESTS = False` CI guardrails. Subsequently addressed 25 code review findings and 13 QA audit findings.

---

## Progress Tracker

### Phase 0: Git Safety

| # | Task | Status |
|---|------|--------|
| 0.1 | Commit current working state on `main` | Done |
| 0.2 | Create branch `feature/agent-system-rebuild` | Done |
| 0.3 | Remove old QA agent (699 lines) | Done |
| 0.4 | Remove old health agent (162 lines) | Done |
| 0.5 | Remove old coordinator (211 lines) | Done |

### Phase 1: Foundation — Deps and Schemas

| # | Task | Status |
|---|------|--------|
| 1.1 | Create `agents/deps/__init__.py` | Done |
| 1.2 | Create `FileScope` with `check_read()`, `check_write()`, `is_readable()`, `_matches()` | Done |
| 1.3 | Create `BaseAgentDeps` (project_root, scope, config) | Done |
| 1.4 | Create `QaAgentDeps(BaseAgentDeps)` with `on_progress` + `emit()` | Done |
| 1.5 | Create `HealthAgentDeps(BaseAgentDeps)` with `app_config` | Done |
| 1.6 | Create `HorizontalAgentDeps(BaseAgentDeps)` with delegation fields | Done |
| 1.7 | Move `Violation` and `QaAuditResult` to shared schemas | Done |
| 1.8 | Move `HealthCheckResult` to shared schemas | Done |

### Phase 2: ComplianceScannerService

| # | Task | Status |
|---|------|--------|
| 2.1 | Create `ComplianceScannerService` class | Done |
| 2.2-2.8 | Extract all config/file helpers from old QA agent | Done |
| 2.9-2.14 | Extract all 6 scanner methods to service | Done |
| 2.15 | Update `scripts/compliance_checker.py` to use service via registry | Done |

### Phase 3: Shared Tool Implementations

| # | Task | Status |
|---|------|--------|
| 3.1 | Create `agents/tools/__init__.py` | Done |
| 3.2-3.3 | `filesystem.py` — `read_file`, `list_files` (scope-enforced) | Done |
| 3.4-3.9 | `compliance.py` — 6 scan wrappers over service | Done |
| 3.10-3.11 | `code.py` — `apply_fix`, `run_tests` (scope-enforced) | Done |
| 3.12-3.13 | `system.py` — `check_system_health`, `get_app_info` | Done |

### Phase 4: Prompt Files

| # | Task | Status |
|---|------|--------|
| 4.1 | `config/prompts/organization/principles.md` | Done |
| 4.2 | `config/prompts/organization/coding_standards.md` | Done |
| 4.3 | `config/prompts/categories/system.md` | Done |
| 4.4 | `config/prompts/categories/code.md` | Done |
| 4.5 | `config/prompts/agents/system/health/system.md` | Done |
| 4.6 | `config/prompts/agents/code/qa/system.md` | Done |

### Phase 5: Coordinator

| # | Task | Status |
|---|------|--------|
| 5.1 | `CoordinatorRequest` / `CoordinatorResponse` typed models | Done |
| 5.2 | `AgentRegistry` with YAML discovery + `@lru_cache` | Done |
| 5.3 | `RuleBasedRouter` with keyword matching | Done |
| 5.4-5.5 | `with_guardrails` (agent-specific limits) + `with_cost_tracking` (dollar cost) | Done |
| 5.6 | `assemble_instructions()` — layered prompt composition | Done |
| 5.7 | `_build_deps()` — FileScope from YAML config | Done |
| 5.8 | Dynamic executor discovery via `importlib.import_module()` | Done |
| 5.9-5.14 | `list_agents`, `_route`, `_execute`, `handle`, `handle_direct`, `handle_direct_stream` | Done |

### Phase 6: Agents (Thin Wrappers)

| # | Task | Status |
|---|------|--------|
| 6.1-6.15 | QA agent — 10 tool wrappers, `run_agent`, `run_agent_stream`, layered prompts | Done (197 lines) |
| 6.16-6.20 | Health agent — 2 tool wrappers, `run_agent`, `run_agent_stream`, layered prompts | Done (88 lines) |

### Phase 7: Configuration

| # | Task | Status |
|---|------|--------|
| 7.1 | QA agent YAML — `agent_type`, `scope`, dotted tools, `max_budget_usd`, `execution.mode` | Done |
| 7.2 | Health agent YAML — same | Done |
| 7.3 | `coordinator.yaml` — hybrid strategy, `llm_model`, `model_pricing`, `redis_ttl`, `approval` | Done |

### Phase 8: API Wiring

| # | Task | Status |
|---|------|--------|
| 8.1 | Agent endpoint imports verified — public interface unchanged | Done |

### Phase 9: Tests

| # | Task | Status |
|---|------|--------|
| 9.1 | `ALLOW_MODEL_REQUESTS = False` in `tests/conftest.py` | Done |
| 9.2-9.7 | ComplianceScannerService unit tests (12 tests) | Done |
| 9.8 | FileScope unit tests (11 tests) | Done |
| 9.9-9.10 | Filesystem + compliance tool tests (5 tests) | Done |
| 9.11 | TestModel agent tests — QA + health (7 tests) | Done |
| 9.12 | Coordinator/registry/router/middleware tests (19 tests) | Done |
| 9.13 | Gateway tests — adapters, rate limiter, startup checks (42 tests) | Done |
| 9.14 | Webhook secret length test (2 tests) | Done |

### Phase 10: Cleanup and Verification

| # | Task | Status |
|---|------|--------|
| 10.1 | All tests passing (416) | Done |
| 10.2 | `scripts/compliance_checker.py` works | Done |
| 10.3 | No linter errors | Done |
| 10.4 | No hardcoded fallbacks in agent system | Done |
| 10.5 | No PydanticAI imports in shared tools | Done |
| 10.6 | No business logic in agent files | Done |

---

## Code Review Fixes (25 findings)

| # | Issue | Status |
|---|-------|--------|
| 1 | Hardcoded executor registration | Fixed — dynamic import via registry |
| 2 | Streaming hardcoded to one agent | Fixed — `hasattr(module, "run_agent_stream")` |
| 3 | QA agent loads own config | Fixed — config from coordinator deps |
| 4 | Health agent loads own config | Fixed — same |
| 5 | No UsageLimits | Fixed — from coordinator.yaml |
| 6 | Cost tracking just a timer | Fixed — computes dollar cost, checks budget |
| 7 | Guardrails ignores agent max_input_length | Fixed — agent-specific limit |
| 8 | Config reloaded every call | Fixed — `@lru_cache` |
| 9 | No fallback routing | Fixed — reads `routing.fallback_agent` |
| 10 | Middleware chain incomplete (memory/output_format) | Deferred — needs doc 46 infrastructure |
| 11 | Conversations in-memory dict | Fixed — removed, stateless streaming |
| 12 | CoordinatorResponse dead code | Fixed — wired into `_format_response()` |
| 13 | CoordinatorRequest dead fields | Documented as reserved for doc 44 |
| 14 | Dead import in health agent | Fixed |
| 15 | API key in agent init | Fixed — `_ensure_api_key()` at coordinator |
| 16 | Coordinator YAML incomplete | Fixed — hybrid, llm_model, redis_ttl, approval |
| 17 | Agent YAMLs missing fields | Fixed — max_budget_usd, execution.mode |
| 18 | Health agent no streaming | Fixed — `run_agent_stream()` added |
| 19 | Response shape varies | Fixed — `_format_response()` standard envelope |
| 20 | No TestModel tests | Fixed — 7 tests with TestModel |
| 21 | ALLOW_MODEL_REQUESTS not exercised | Fixed — guard verified in test |
| 22 | Gateway zero test coverage | Fixed — 42 tests |
| 23 | FileScope._matches() redundant | Fixed — normalized path comparison |
| 24 | load_config() coupling | Fixed — removed from service |
| 25 | Registry singleton pattern | Fixed — `@lru_cache` |

---

## QA Audit Fixes (22 findings)

| # | Criticality | Finding | Status |
|---|-------------|---------|--------|
| 1 | CRITICAL | Startup checks skip webhook_secret_min_length | Fixed + tested |
| 2 | HIGH | API key via os.environ.setdefault | Open — needs PydanticAI provider research |
| 3 | HIGH | Raw yaml.safe_load without Pydantic validation | Open — needs agent config schema design |
| 4 | HIGH | Guardrails dict subscript fails at runtime | Open — tied to #3 |
| 5 | HIGH | Unused imports in coordinator.py | Fixed |
| 6 | HIGH | TELEGRAM_MAX_MESSAGE_LENGTH hardcoded | Fixed — reads from config |
| 7 | HIGH | USER_ROLES hardcoded | Open — needs config schema extension |
| 8 | HIGH | Global mutable singletons (systemic) | Fixed — registry-managed agent lifecycle (plan 05) |
| 9 | HIGH | _conversations unbounded dict | Fixed — removed, stateless |
| 10 | HIGH | max_delegation_depth hardcoded | Fixed |
| 11 | MEDIUM | Mock-heavy tests (systemic) | Open — largest effort, 15 files |
| 12 | MEDIUM | os.environ.get fallback in test conftest | Accepted-by-design |
| 13 | MEDIUM | Dead frontend references | Fixed |
| 14 | MEDIUM | cli.py 706 lines | Open — needs extraction into submodules |
| 15 | MEDIUM | Zero coordinator test coverage | Fixed — 19 tests |
| 16 | MEDIUM | No repository tests | Open — separate coverage effort |
| 17 | MEDIUM | Empty test directories | Fixed — removed |
| 18 | MEDIUM | Registry silently skips malformed configs | Fixed — logs warnings |
| 19 | LOW | Unused typer dependency | Fixed |
| 20 | LOW | dead_code_detector violates standards | Open — standalone rewrite |
| 21 | LOW | Role assignment by position | Open — tied to #7 |
| 22 | LOW | Hardcoded test DB params | Open — low priority |

---

## Remaining Open Items

| # | Finding | Effort | Blocked By |
|---|---------|--------|-----------|
| 2 | API key injection pattern | Small | PydanticAI provider API research |
| 3/4 | Pydantic schemas for agent configs | Medium | Schema design decision |
| 7/21 | USER_ROLES to config + role mapping | Medium | Config schema extension |
| 8 | Global singleton lifecycle | Large | Architectural decision |
| 11 | Mock-heavy test rewrite | Large | Test strategy decision |
| 14 | cli.py split into submodules | Medium | None |
| 16 | Repository test coverage | Medium | None |
| 20 | dead_code_detector rewrite | Medium | None |

---

## Branch Summary

```
feature/agent-system-rebuild (9 commits)

c8bb337 Remove old agent code — clean slate for rebuild
3099e1a Rebuild agent system from scratch per doc 47
990ee08 Fix 17 code review issues in agent system
f346cf5 Align agent system with doc 47 spec — fix 6 remaining issues
bb0ff03 Move model pricing from hardcoded constants to coordinator.yaml
cb96eaf Remove all hardcoded fallback values from agent system
a8d2f14 Add gateway test coverage (#22) — 42 tests
438e371 Fix QA audit findings: #1 critical + 6 quick fixes
33a641a Fix QA audit findings: #6, #9, #15 + bonus #73
```

**416 tests passing. Zero linter errors.**
