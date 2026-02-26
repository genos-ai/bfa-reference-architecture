# Implementation Plan: QA Compliance Agent (`code.qa.agent`)

*Created: 2026-02-25*
*Status: Implemented*

---

## Progress Tracker

| # | Task | File(s) Affected | Status |
|---|------|-----------------|--------|
| 1 | Rename `health_agent` → `system.health.agent` (config) | `config/agents/system/health/agent.yaml` | Done |
| 2 | Rename `health_agent` → `system.health.agent` (code) | `modules/backend/agents/vertical/system/health/agent.py` | Done |
| 3 | Update coordinator: `system.health.agent`, glob `**/agent.yaml` | `modules/backend/agents/coordinator/coordinator.py` | Done |
| 4 | Verify existing tests still pass after rename (300 passed) | All test files | Done |
| 5 | Create `code.qa.agent` YAML config with rules and exclusions | `config/agents/code/qa/agent.yaml` | Done |
| 6 | Create agent file with output schemas (`Violation`, `QaAuditResult`) | `modules/backend/agents/vertical/code/qa/agent.py` | Done |
| 7 | Implement `list_python_files` tool | `agent.py` | Done |
| 8 | Implement `scan_import_violations` tool | `agent.py` | Done |
| 9 | Implement `scan_datetime_violations` tool | `agent.py` | Done |
| 10 | Implement `scan_hardcoded_values` tool | `agent.py` | Done |
| 11 | Implement `scan_file_sizes` tool | `agent.py` | Done |
| 12 | Implement `scan_cli_options` tool | `agent.py` | Done |
| 13 | Implement `scan_config_files` tool | `agent.py` | Done |
| 14 | Implement `read_source_file` tool | `agent.py` | Done |
| 15 | Implement `apply_fix` tool (string replacement) | `agent.py` | Done |
| 16 | Implement `run_tests` tool (pytest execution, returns pass/fail) | `agent.py` | Done |
| 17 | Wire up PydanticAI Agent, system prompt, `run_qa_agent()` entry | `agent.py` | Done |
| 18 | Refactor coordinator `_execute()` to registry-driven dispatch | `coordinator.py` | Done |
| 19 | Register `code.qa.agent` executor in coordinator | `coordinator.py` | Done |
| 20 | Write unit tests for scanner tools (32 tests, real temp files) | `tests/unit/backend/agents/test_code_qa.py` | Done |
| 21 | Write agent integration tests with TestModel | `test_code_qa.py` | Done |
| 22 | Run full test suite — 332 passed, zero failures | All test files | Done |
| 23 | Restructure to directory-per-agent pattern (`{category}/{name}/agent.py`) | All agent files | Done |
| 24 | Update reference architecture doc 26 with naming + directory conventions | `docs/99-reference-architecture/41-agentic-pydanticai.md` | Done |

---

## Background

A manual audit of the codebase identified recurring rule violations: hardcoded constants, mocked tests, `os.getenv()` with fallbacks, and other patterns that contradict the project's coding standards (AGENTS.md, core principles P5/P7/P8). These violations accumulate between audits and are tedious to catch manually.

This plan added a **QA compliance agent** (`code.qa.agent`) — a vertical agent that audits the codebase for rule violations, **fixes them**, and escalates design decisions to the human for approval before fixing. It follows the exact same pattern as the health agent, registers in the coordinator, and is callable through all existing channels (CLI, TUI, Telegram, API).

### Agent Naming Convention

Established during this implementation per **41-agentic-pydanticai.md** "Agent Naming Convention". All agents use the `{category}.{name}.agent` format with directory-per-agent structure:

| Agent Identity | Config Path | Code Path |
|---------------|-------------|-----------|
| `system.health.agent` | `config/agents/system/health/agent.yaml` | `modules/backend/agents/vertical/system/health/agent.py` |
| `code.qa.agent` | `config/agents/code/qa/agent.yaml` | `modules/backend/agents/vertical/code/qa/agent.py` |

Categories: `system` (platform), `code` (source code), `security`, `data`, `domain` (business), `comms`.

### Design Principles

- The agent is a permanent platform capability, not a one-off script
- Detection is deterministic (AST/regex tools) — the LLM reasons about findings, not detection
- The agent fixes violations directly — it does not just report and leave the work to the human
- For design decisions (where to put config values, how to restructure), the agent asks the human, then applies the chosen fix
- The agent runs on a cheap model (Haiku) since its tools do the heavy lifting
- All checker rules are defined in YAML config, not hardcoded in the agent
- After fixing, the agent runs tests to verify nothing broke

---

## Architecture

```
chat.py / tui.py / Telegram / API
    │
    ▼
Coordinator (keyword route: "compliance", "qa", "audit", "violations")
    │
    ▼
┌──────────────────────────────────────────────────────┐
│            code.qa.agent (Haiku)                      │
│                                                      │
│  Scanner Tools (deterministic, no LLM):              │
│    scan_hardcoded_values()                            │
│    scan_import_violations()                           │
│    scan_datetime_violations()                         │
│    scan_cli_options()                                 │
│    scan_file_sizes()                                  │
│    scan_config_files()                                │
│    list_python_files()                                │
│                                                      │
│  Action Tools:                                       │
│    read_source_file(path)  — inspect file context    │
│    apply_fix(path, old, new) — modify source file    │
│    run_tests()             — execute pytest           │
│                                                      │
│  LLM (Haiku) reasons about findings:                 │
│    - Classifies severity                             │
│    - Applies clear fixes directly via apply_fix      │
│    - Asks human for design decisions before fixing   │
│    - Runs tests after fixes to verify correctness    │
│    - Produces structured QaAuditResult output        │
│                                                      │
└──────────────────────────────────────────────────────┘
    │
    ▼
QaAuditResult (structured output with fix status per violation)
```

### Agent Workflow (Single Invocation)

```
1. SCAN        Use scanner tools to detect all violations
2. CLASSIFY    For each violation, determine: auto_fixable or needs_human
3. FIX AUTO    Apply fixes for auto_fixable violations via apply_fix
4. ASK HUMAN   Present design decisions with options for needs_human violations
5. FIX HUMAN   After human answers, apply the chosen fix via apply_fix
6. TEST        Run pytest to verify no regressions
7. REPORT      Return QaAuditResult with all violations and their fix status
```

### How HITL Works

**Auto-fixable** — The agent applies the fix directly without asking. Examples:
- Replace `datetime.now()` with `utc_now()` and add the import
- Replace `from .foo import bar` with `from modules.x.foo import bar`

**Needs human decision** — The agent presents the question with concrete options in its output, then the human responds with a follow-up message. The agent applies the chosen fix on the next invocation.

---

## What Was Built

### New Files

| File | Purpose | Lines |
|------|---------|-------|
| `config/agents/system/health/agent.yaml` | Renamed health agent config | 27 |
| `config/agents/code/qa/agent.yaml` | QA agent config (model, 10 rules, exclusions) | 88 |
| `modules/backend/agents/vertical/system/health/agent.py` | Renamed health agent code | 152 |
| `modules/backend/agents/vertical/system/health/__init__.py` | Package marker | 1 |
| `modules/backend/agents/vertical/code/__init__.py` | Package marker | 1 |
| `modules/backend/agents/vertical/code/qa/__init__.py` | Package marker | 1 |
| `modules/backend/agents/vertical/code/qa/agent.py` | QA agent (10 tools, schemas, entry point) | 478 |
| `tests/unit/backend/agents/__init__.py` | Package marker | 0 |
| `tests/unit/backend/agents/test_code_qa.py` | 32 tests (real temp files, no mocks) | 443 |

### Deleted Files

| File | Reason |
|------|--------|
| `config/agents/health_agent.yaml` | Renamed to `system/health/agent.yaml` |
| `modules/backend/agents/vertical/health_agent.py` | Renamed to `system/health/agent.py` |

### Modified Files

| File | Change |
|------|--------|
| `modules/backend/agents/coordinator/coordinator.py` | Recursive `**/agent.yaml` glob, registry-driven dispatch, both agents registered |
| `chat.py` | Docstring references updated to `system.health.agent` |
| `docs/99-reference-architecture/41-agentic-pydanticai.md` | Added "Agent Naming Convention" section, updated module structure, file naming, config examples, walkthrough |

---

## Scanner Tools Implemented

| Tool | Detection Method | What It Finds |
|------|-----------------|---------------|
| `list_python_files` | Directory walk with exclusion filtering | All `.py` files in scope |
| `scan_import_violations` | Regex: `^from \.`, `^import logging$` in `modules/`, `os.getenv(` with 2+ args | Relative imports, direct logging, env fallbacks |
| `scan_datetime_violations` | Regex: `datetime.now()`, `datetime.utcnow()` | Deprecated/incorrect datetime usage |
| `scan_hardcoded_values` | AST: module-level `Assign` with `UPPER_CASE` name and literal `Constant` value | `RATE_LIMIT_WINDOW = 60`, `MAX_LENGTH = 4096` |
| `scan_file_sizes` | Line count per `.py` file | Files exceeding `file_size_limit` from config |
| `scan_cli_options` | AST: `argparse.add_argument` with positional args; missing `--verbose`/`--debug` | Positional CLI args, missing debug options |
| `scan_config_files` | Regex: check first 500 chars of YAML files for `# ===` comment block | YAML files missing option headers |

## Action Tools Implemented

| Tool | Behavior |
|------|----------|
| `read_source_file(path)` | Returns file contents with line numbers for LLM context |
| `apply_fix(path, old, new)` | Exact string replacement; fails if old_text not found or ambiguous |
| `run_tests()` | Executes `pytest tests/unit -v --tb=short`, returns pass/fail + output tail |

---

## Test Results

**332 tests passed, zero failures.** (300 existing + 32 new)

Test categories:
- Exclusion helpers (4 tests)
- Rule config parsing (2 tests)
- File discovery (3 tests)
- Import violation scanning (3 tests)
- Datetime violation scanning (1 test)
- Hardcoded value scanning (3 tests)
- File size scanning (2 tests)
- Config file header scanning (2 tests)
- Apply fix logic (3 tests)
- Output schema validation (4 tests)
- Config loading from YAML (5 tests)

All tool tests use real temporary files via `tmp_path`. No mocking.

---

## Usage

```bash
# Via keyword routing
python chat.py --message "run compliance audit" --verbose

# Via direct invocation
python chat.py --agent code.qa.agent --message "audit the codebase" --verbose

# List all agents
python chat.py --list-agents
```

---

## Rules Compliance

| Rule | Status |
|------|--------|
| No hardcoded values | Rules and limits defined in YAML config |
| Absolute imports only | All imports absolute (`from modules.backend.core...`) |
| Centralized logging | Uses `get_logger(__name__)` |
| `.project_root` for root discovery | Uses `find_project_root()` from core.config |
| `--verbose`/`--debug` on scripts | Agent invoked through existing entry scripts |
| Centralized `.env` for secrets | No new secrets — uses existing `ANTHROPIC_API_KEY` |
| No hardcoded fallbacks | Missing config = startup failure |
| No helper/wrapper scripts | Agent is a vertical agent, not a script |
| Files under 1000 lines | `agent.py` = 478 lines, test file = 443 lines |
| Minimal `__init__.py` | All `__init__.py` files are 1-line package markers |
| No mocked tests | Tool tests use real temp files; schemas tested directly |
| Fail fast | Missing YAML config raises `FileNotFoundError` at agent init |
| Agent naming convention | `code.qa.agent` follows `{category}.{name}.agent` per doc 26 |
| Directory-per-agent | `{category}/{name}/agent.py` and `{category}/{name}/agent.yaml` |

---

## Future Enhancements (Out of Scope)

1. **Scheduled audits** — taskiq cron job runs `code.qa.agent` daily, posts results to Telegram
2. **Iterative loop mode** — agent re-scans after fixes and loops until zero violations or max iterations
3. **CI gate** — run the agent in CI and fail the build on error-severity violations
4. **Rule expansion** — test quality, docstring coverage, type annotation rules
5. **Baseline tracking** — store results in database, report "3 new violations since last audit"
6. **Custom rules** — user-defined regex/AST rules in YAML without modifying agent code
7. **YAML config modification** — `apply_config_fix` tool that can add keys to YAML files when moving hardcoded values to config
