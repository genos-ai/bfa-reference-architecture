# Implementation Plan: Agent Config Schemas + CLI Split

*Created: 2026-02-26*
*Status: Complete*
*Branch: `feature/config-schemas-cli-split` (2 commits, 507 tests passing)*
*Fixes: QA audit findings #3, #4, #14*

---

## Summary

Two workstreams that harden the foundation before building new features:

**Workstream A — Pydantic schemas for agent configs (findings #3/#4).** Replace raw `yaml.safe_load()` dicts with validated Pydantic schemas. Catches typos, missing keys, and wrong types at load time instead of runtime `KeyError` deep in execution. Follows the exact pattern established in `modules/backend/core/config_schema.py`.

**Workstream B — cli.py split into submodules (finding #14).** Extract 9 service handlers from the 706-line monolith into `modules/backend/cli/` submodules. Keeps `cli.py` at project root as the entry point (per doc 28). Each handler becomes a replaceable module.

---

## Phase 0: Git Safety

| # | Task | File/Command |
|---|------|-------------|
| 0.1 | Commit any uncommitted work on current branch | `git add -A && git commit -m "WIP: save state before config-schemas-cli-split"` |
| 0.2 | Create feature branch from current branch | `git checkout -b feature/config-schemas-cli-split` |
| 0.3 | Backup files that will be modified | Copy originals to `_backups/` (gitignored temp dir) |

**Backup list (for reference during implementation):**

```
_backups/
├── registry.py                    ← modules/backend/agents/coordinator/registry.py
├── middleware.py                  ← modules/backend/agents/coordinator/middleware.py
├── coordinator.py                 ← modules/backend/agents/coordinator/coordinator.py
├── base.py                        ← modules/backend/agents/deps/base.py
├── qa_agent.py                    ← modules/backend/agents/vertical/code/qa/agent.py
├── health_agent.py                ← modules/backend/agents/vertical/system/health/agent.py
├── compliance_tools.py            ← modules/backend/agents/tools/compliance.py
├── compliance_checker.py          ← scripts/compliance_checker.py
├── cli.py                         ← cli.py
├── test_coordinator.py            ← tests/unit/backend/agents/test_coordinator.py
└── test_agent_testmodel.py        ← tests/unit/backend/agents/test_agent_testmodel.py
```

---

## Workstream A: Pydantic Schemas for Agent Configs

### Phase A1: Create Schema File

**Create `modules/backend/agents/config_schema.py`**

This file defines Pydantic schemas for both agent YAML configs (`config/agents/**/agent.yaml`) and the coordinator YAML config (`config/agents/coordinator.yaml`). Follows the `_StrictBase` pattern from `modules/backend/core/config_schema.py`.

```python
"""
Agent Configuration Schemas.

Pydantic models defining the expected structure of agent and coordinator
YAML config files. Used by AgentRegistry and middleware to validate
configuration at load time.

Each top-level class corresponds to one config file:
    AgentConfigSchema       → config/agents/**/agent.yaml
    CoordinatorConfigSchema → config/agents/coordinator.yaml
"""

from pydantic import BaseModel, ConfigDict, Field


class _StrictBase(BaseModel):
    """Base with extra='forbid' so unknown YAML keys are caught immediately."""

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Agent config schemas (config/agents/**/agent.yaml)
# =============================================================================


class FileScopeConfigSchema(_StrictBase):
    """Filesystem access control for an agent."""

    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)


class ExecutionSchema(_StrictBase):
    """Agent execution environment."""

    mode: str


class ComplianceRuleSchema(_StrictBase):
    """A single compliance rule definition."""

    id: str
    description: str
    severity: str
    enabled: bool


class ExclusionsSchema(_StrictBase):
    """Paths and patterns excluded from scanning."""

    paths: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)


class AgentConfigSchema(_StrictBase):
    """Schema for config/agents/**/agent.yaml files.

    Common fields are required. Agent-specific fields (rules, exclusions,
    file_size_limit) are optional — absent in agents that don't need them.
    """

    agent_name: str
    agent_type: str
    description: str
    enabled: bool
    model: str
    keywords: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    max_input_length: int
    max_budget_usd: float
    execution: ExecutionSchema
    scope: FileScopeConfigSchema = Field(default_factory=FileScopeConfigSchema)

    # QA-agent-specific (optional for other agents)
    file_size_limit: int | None = None
    rules: list[ComplianceRuleSchema] | None = None
    exclusions: ExclusionsSchema | None = None


# =============================================================================
# Coordinator config schema (config/agents/coordinator.yaml)
# =============================================================================


class ModelPricingRateSchema(_StrictBase):
    """Cost per million tokens for a specific model."""

    input: float
    output: float


class RoutingSchema(_StrictBase):
    """Agent routing configuration."""

    strategy: str
    llm_model: str
    complex_request_agent: str
    fallback_agent: str
    max_routing_depth: int


class CoordinatorLimitsSchema(_StrictBase):
    """Budget and safety limits."""

    max_requests_per_task: int
    max_tool_calls_per_task: int
    max_tokens_per_task: int
    max_cost_per_plan: float
    max_cost_per_user_daily: float
    task_timeout_seconds: int
    plan_timeout_seconds: int


class GuardrailsSchema(_StrictBase):
    """Input validation and injection blocking."""

    max_input_length: int
    injection_patterns: list[str]


class RedisTtlSchema(_StrictBase):
    """Redis key TTLs in seconds."""

    session: int
    approval: int
    lock: int
    result: int


class ApprovalSchema(_StrictBase):
    """Human-in-the-loop approval settings."""

    poll_interval_seconds: int
    timeout_seconds: int


class CoordinatorConfigSchema(_StrictBase):
    """Schema for config/agents/coordinator.yaml."""

    model_pricing: dict[str, ModelPricingRateSchema]
    routing: RoutingSchema
    limits: CoordinatorLimitsSchema
    guardrails: GuardrailsSchema
    redis_ttl: RedisTtlSchema
    approval: ApprovalSchema
```

**Verification:** Import the module and validate both YAML files:

```python
import yaml
from modules.backend.agents.config_schema import AgentConfigSchema, CoordinatorConfigSchema

with open("config/agents/code/qa/agent.yaml") as f:
    AgentConfigSchema(**yaml.safe_load(f))  # must not raise

with open("config/agents/system/health/agent.yaml") as f:
    AgentConfigSchema(**yaml.safe_load(f))  # must not raise

with open("config/agents/coordinator.yaml") as f:
    CoordinatorConfigSchema(**yaml.safe_load(f))  # must not raise
```

---

### Phase A2: Update Registry to Validate on Load

**Modify `modules/backend/agents/coordinator/registry.py`**

The registry currently stores raw dicts. Change it to validate each agent config YAML through `AgentConfigSchema` at load time and store the validated schema instance.

**Changes:**

1. Add import:

```python
from pydantic import ValidationError
from modules.backend.agents.config_schema import AgentConfigSchema
```

2. Change `_agents` type annotation:

```python
# BEFORE
self._agents: dict[str, dict[str, Any]] = {}

# AFTER
self._agents: dict[str, AgentConfigSchema] = {}
```

3. In `_ensure_loaded()`, validate after `yaml.safe_load()`:

```python
# BEFORE (lines 37-56)
config = yaml.safe_load(f)
# ... checks ...
self._agents[name] = config

# AFTER
raw = yaml.safe_load(f)
# ... null/name checks stay the same but use raw instead of config ...

try:
    config = AgentConfigSchema(**raw)
except ValidationError as e:
    logger.error(
        "Invalid agent config",
        extra={"path": str(path), "error": str(e)},
    )
    continue

if not config.enabled:
    logger.debug("Agent disabled", extra={"agent_name": config.agent_name})
    continue

self._agents[config.agent_name] = config
```

4. Update `get()` return type:

```python
# BEFORE
def get(self, agent_name: str) -> dict[str, Any]:

# AFTER
def get(self, agent_name: str) -> AgentConfigSchema:
```

5. Update `list_all()` to use attribute access:

```python
# BEFORE
return [
    {
        "agent_name": config["agent_name"],
        "description": config.get("description", ""),
        "keywords": config.get("keywords", []),
        "tools": config.get("tools", []),
    }
    for config in self._agents.values()
]

# AFTER
return [
    {
        "agent_name": config.agent_name,
        "description": config.description,
        "keywords": config.keywords,
        "tools": config.tools,
    }
    for config in self._agents.values()
]
```

6. Update `get_by_keyword()` to use attribute access:

```python
# BEFORE
for keyword in config.get("keywords", []):

# AFTER
for keyword in config.keywords:
```

7. Update `resolve_module_path()` to use attribute access:

```python
# BEFORE
agent_type = config.get("agent_type", "vertical")

# AFTER
agent_type = config.agent_type
```

8. Remove unused `from typing import Any` import if no longer needed.

---

### Phase A3: Update Middleware to Validate Coordinator Config

**Modify `modules/backend/agents/coordinator/middleware.py`**

The middleware currently loads `coordinator.yaml` as a raw dict. Change `_load_coordinator_config()` to validate through `CoordinatorConfigSchema` and update all access patterns to use typed attributes.

**Changes:**

1. Add imports:

```python
from pydantic import ValidationError
from modules.backend.agents.config_schema import AgentConfigSchema, CoordinatorConfigSchema
```

2. Update `_load_coordinator_config()`:

```python
# BEFORE
@lru_cache(maxsize=1)
def _load_coordinator_config() -> dict[str, Any]:
    config_path = find_project_root() / "config" / "agents" / "coordinator.yaml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}

# AFTER
@lru_cache(maxsize=1)
def _load_coordinator_config() -> CoordinatorConfigSchema:
    config_path = find_project_root() / "config" / "agents" / "coordinator.yaml"
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return CoordinatorConfigSchema(**raw)
```

Note: Remove the `if not config_path.exists(): return {}` guard. If coordinator.yaml is missing, it's a startup error — fail fast.

3. Update `compute_cost_usd()`:

```python
# BEFORE
config = _load_coordinator_config()
pricing = config.get("model_pricing", {})
default_rates = pricing.get("default", {})
rates = pricing.get(model or "", default_rates)
input_cost = (input_tokens / 1_000_000) * rates["input"]
output_cost = (output_tokens / 1_000_000) * rates["output"]

# AFTER
config = _load_coordinator_config()
default_rates = config.model_pricing.get("default")
rates = config.model_pricing.get(model or "", default_rates)
if rates is None:
    rates = default_rates
input_cost = (input_tokens / 1_000_000) * rates.input
output_cost = (output_tokens / 1_000_000) * rates.output
```

4. Update `with_guardrails()` — change parameter type and access:

```python
# BEFORE
def with_guardrails(agent_config: dict[str, Any] | None = None):
    ...
    coordinator_config = _load_coordinator_config()
    guardrails = coordinator_config.get("guardrails", {})
    coordinator_max = guardrails["max_input_length"]
    agent_max = (agent_config or {}).get("max_input_length")
    ...
    patterns = guardrails.get("injection_patterns", [])

# AFTER
def with_guardrails(agent_config: AgentConfigSchema | None = None):
    ...
    coordinator_config = _load_coordinator_config()
    coordinator_max = coordinator_config.guardrails.max_input_length
    agent_max = agent_config.max_input_length if agent_config else None
    ...
    patterns = coordinator_config.guardrails.injection_patterns
```

5. Update `with_cost_tracking()`:

```python
# BEFORE
coordinator_config = _load_coordinator_config()
limits = coordinator_config.get("limits", {})
max_cost_plan = limits.get("max_cost_per_plan")

# AFTER
coordinator_config = _load_coordinator_config()
max_cost_plan = coordinator_config.limits.max_cost_per_plan
```

---

### Phase A4: Update Coordinator to Use Typed Access

**Modify `modules/backend/agents/coordinator/coordinator.py`**

The coordinator currently receives agent configs as dicts from the registry. Since registry now returns `AgentConfigSchema`, update all access patterns.

**Changes:**

1. Add import:

```python
from modules.backend.agents.config_schema import AgentConfigSchema
```

2. Update `build_deps_from_config()`:

```python
# BEFORE
def build_deps_from_config(agent_config: dict[str, Any]) -> dict[str, Any]:
    scope_config = agent_config.get("scope", {})
    scope = FileScope(
        read_paths=scope_config.get("read", []),
        write_paths=scope_config.get("write", []),
    )
    return {
        "project_root": find_project_root(),
        "scope": scope,
        "config": agent_config,
    }

# AFTER
def build_deps_from_config(agent_config: AgentConfigSchema) -> dict[str, Any]:
    scope = FileScope(
        read_paths=agent_config.scope.read,
        write_paths=agent_config.scope.write,
    )
    return {
        "project_root": find_project_root(),
        "scope": scope,
        "config": agent_config,
    }
```

3. Update `_build_agent_deps()` parameter type:

```python
# BEFORE
def _build_agent_deps(agent_name: str, agent_config: dict[str, Any]) -> BaseAgentDeps:

# AFTER
def _build_agent_deps(agent_name: str, agent_config: AgentConfigSchema) -> BaseAgentDeps:
```

4. Update `_get_usage_limits()`:

```python
# BEFORE
config = _load_coordinator_config()
limits = config.get("limits", {})
return UsageLimits(
    request_limit=limits["max_requests_per_task"],
    total_tokens_limit=limits["max_tokens_per_task"],
)

# AFTER
config = _load_coordinator_config()
return UsageLimits(
    request_limit=config.limits.max_requests_per_task,
    total_tokens_limit=config.limits.max_tokens_per_task,
)
```

5. Update `_execute_agent()` parameter type:

```python
# BEFORE
async def _execute_agent(
    agent_name: str,
    user_input: str,
    agent_config: dict[str, Any],
) -> dict[str, Any]:

# AFTER
async def _execute_agent(
    agent_name: str,
    user_input: str,
    agent_config: AgentConfigSchema,
) -> dict[str, Any]:
```

6. Update fallback routing in `handle()` and `route()`:

```python
# BEFORE
coordinator_config = _load_coordinator_config()
fallback = coordinator_config.get("routing", {}).get("fallback_agent")

# AFTER
coordinator_config = _load_coordinator_config()
fallback = coordinator_config.routing.fallback_agent
```

---

### Phase A5: Update Deps Dataclass

**Modify `modules/backend/agents/deps/base.py`**

Change `BaseAgentDeps.config` from `dict[str, Any]` to `AgentConfigSchema`.

```python
# BEFORE
from typing import Any

@dataclass
class BaseAgentDeps:
    project_root: Path
    scope: FileScope
    config: dict[str, Any] = field(default_factory=dict)

# AFTER
from modules.backend.agents.config_schema import AgentConfigSchema

@dataclass
class BaseAgentDeps:
    project_root: Path
    scope: FileScope
    config: AgentConfigSchema | None = None
```

Note: Use `AgentConfigSchema | None = None` instead of `Field(default_factory=...)` because dataclasses use `field()`, not `Field()`. The `None` default preserves backward compatibility for cases where deps are constructed without config (e.g., tests that only need scope).

Remove `from typing import Any` if no longer needed (check other usages in file first — `HorizontalAgentDeps.coordinator` uses `Any`).

---

### Phase A6: Update Agent Implementations

**Modify `modules/backend/agents/vertical/code/qa/agent.py`**

1. Update config access in `list_python_files` tool:

```python
# BEFORE
exclusions = set(ctx.deps.config.get("exclusions", {}).get("paths", []))

# AFTER
exclusions = set(ctx.deps.config.exclusions.paths) if ctx.deps.config.exclusions else set()
```

2. Update model access in `run_agent()`:

```python
# BEFORE
model = deps.config["model"]

# AFTER
model = deps.config.model
```

3. Update model access in `run_agent_stream()` `_run()` inner function:

```python
# BEFORE
model = deps.config["model"]

# AFTER
model = deps.config.model
```

**Modify `modules/backend/agents/vertical/system/health/agent.py`**

1. Update model access in `run_agent()`:

```python
# BEFORE
model = deps.config["model"]

# AFTER
model = deps.config.model
```

---

### Phase A7: Update Compliance Tools

**Modify `modules/backend/agents/tools/compliance.py`**

The tools currently accept `config: dict[str, Any]` and pass it to `ComplianceScannerService`. Change to accept `AgentConfigSchema` and convert to dict at the service boundary.

1. Update imports:

```python
# BEFORE
from typing import Any
from modules.backend.agents.deps.base import FileScope

# AFTER
from modules.backend.agents.config_schema import AgentConfigSchema
from modules.backend.agents.deps.base import FileScope
```

2. Update `_get_scanner()`:

```python
# BEFORE
def _get_scanner(project_root: Path, config: dict[str, Any]) -> ComplianceScannerService:
    return ComplianceScannerService(project_root, config)

# AFTER
def _get_scanner(project_root: Path, config: AgentConfigSchema) -> ComplianceScannerService:
    return ComplianceScannerService(project_root, config.model_dump())
```

3. Update all 6 scan function signatures — change `config: dict[str, Any]` to `config: AgentConfigSchema`:

```python
async def scan_imports(
    project_root: Path, scope: FileScope, config: AgentConfigSchema,
) -> list[dict]:
```

Repeat for: `scan_datetime`, `scan_hardcoded`, `scan_file_sizes`, `scan_cli_options`, `scan_config_files`.

4. Remove `from typing import Any` import.

---

### Phase A8: Update Compliance Checker Script

**Modify `scripts/compliance_checker.py`**

The script gets config from the registry (now returns `AgentConfigSchema`) and passes it to `ComplianceScannerService` (still expects dict).

```python
# BEFORE (lines 66-74)
config = get_registry().get("code.qa.agent")
logger.info("Loaded config", extra={"rules": len(config.get("rules", []))})

project_root = find_project_root()
scanner = ComplianceScannerService(project_root, config)
findings = scanner.scan_all()

for f in findings:
    f["severity"] = scanner.get_rule_severity(f["rule_id"])

# AFTER
config = get_registry().get("code.qa.agent")
logger.info("Loaded config", extra={"rules": len(config.rules or [])})

project_root = find_project_root()
scanner = ComplianceScannerService(project_root, config.model_dump())
findings = scanner.scan_all()

for f in findings:
    f["severity"] = scanner.get_rule_severity(f["rule_id"])
```

---

### Phase A9: Update Tests

**Modify `tests/unit/backend/agents/test_coordinator.py`**

1. Update `TestAgentRegistry.test_get_returns_config()`:

```python
# BEFORE
def test_get_returns_config(self):
    registry = get_registry()
    config = registry.get("code.qa.agent")
    assert config["agent_name"] == "code.qa.agent"
    assert config["enabled"] is True
    assert "model" in config

# AFTER
def test_get_returns_config(self):
    from modules.backend.agents.config_schema import AgentConfigSchema

    registry = get_registry()
    config = registry.get("code.qa.agent")
    assert isinstance(config, AgentConfigSchema)
    assert config.agent_name == "code.qa.agent"
    assert config.enabled is True
    assert config.model is not None
```

2. Update `TestMiddleware.test_coordinator_config_loads()`:

```python
# BEFORE
def test_coordinator_config_loads(self):
    config = _load_coordinator_config()
    assert "routing" in config
    assert "limits" in config
    assert "guardrails" in config

# AFTER
def test_coordinator_config_loads(self):
    from modules.backend.agents.config_schema import CoordinatorConfigSchema

    config = _load_coordinator_config()
    assert isinstance(config, CoordinatorConfigSchema)
    assert config.routing is not None
    assert config.limits is not None
    assert config.guardrails is not None
```

**Modify `tests/unit/backend/agents/test_agent_testmodel.py`**

The `qa_deps` and `health_deps` fixtures currently pass the registry dict to deps. Since registry now returns `AgentConfigSchema`, this works automatically — no changes needed. Verify the fixtures still work.

**Create `tests/unit/backend/agents/test_config_schema.py`** — new test file:

```python
"""
Unit tests for agent configuration schemas.

Validates that real YAML config files pass schema validation, and that
malformed configs are caught with clear errors.
"""

import pytest
import yaml

from modules.backend.agents.config_schema import (
    AgentConfigSchema,
    CoordinatorConfigSchema,
)
from modules.backend.core.config import find_project_root


class TestAgentConfigSchema:
    """Tests for agent YAML schema validation."""

    def test_qa_agent_config_validates(self):
        path = find_project_root() / "config" / "agents" / "code" / "qa" / "agent.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = AgentConfigSchema(**raw)
        assert config.agent_name == "code.qa.agent"
        assert config.agent_type == "vertical"
        assert config.enabled is True
        assert len(config.rules) > 0
        assert config.exclusions is not None

    def test_health_agent_config_validates(self):
        path = find_project_root() / "config" / "agents" / "system" / "health" / "agent.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = AgentConfigSchema(**raw)
        assert config.agent_name == "system.health.agent"
        assert config.rules is None
        assert config.exclusions is None

    def test_rejects_unknown_field(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="extra"):
            AgentConfigSchema(
                agent_name="test.agent",
                agent_type="vertical",
                description="test",
                enabled=True,
                model="anthropic:test",
                max_input_length=1000,
                max_budget_usd=1.0,
                execution={"mode": "local"},
                unknown_field="should fail",
            )

    def test_rejects_missing_required_field(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentConfigSchema(
                agent_name="test.agent",
                # missing agent_type, description, etc.
            )

    def test_model_dump_produces_dict(self):
        path = find_project_root() / "config" / "agents" / "code" / "qa" / "agent.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = AgentConfigSchema(**raw)
        dumped = config.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["agent_name"] == "code.qa.agent"


class TestCoordinatorConfigSchema:
    """Tests for coordinator YAML schema validation."""

    def test_coordinator_config_validates(self):
        path = find_project_root() / "config" / "agents" / "coordinator.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = CoordinatorConfigSchema(**raw)
        assert config.routing.strategy == "hybrid"
        assert config.limits.max_requests_per_task > 0
        assert config.guardrails.max_input_length > 0
        assert len(config.model_pricing) > 0

    def test_pricing_rates_accessible(self):
        path = find_project_root() / "config" / "agents" / "coordinator.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = CoordinatorConfigSchema(**raw)
        default_rates = config.model_pricing.get("default")
        assert default_rates is not None
        assert default_rates.input > 0
        assert default_rates.output > 0

    def test_rejects_unknown_field(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="extra"):
            CoordinatorConfigSchema(
                model_pricing={},
                routing={
                    "strategy": "rule",
                    "llm_model": "test",
                    "complex_request_agent": "test",
                    "fallback_agent": "test",
                    "max_routing_depth": 1,
                },
                limits={
                    "max_requests_per_task": 1,
                    "max_tool_calls_per_task": 1,
                    "max_tokens_per_task": 1,
                    "max_cost_per_plan": 1.0,
                    "max_cost_per_user_daily": 1.0,
                    "task_timeout_seconds": 1,
                    "plan_timeout_seconds": 1,
                },
                guardrails={"max_input_length": 1, "injection_patterns": []},
                redis_ttl={"session": 1, "approval": 1, "lock": 1, "result": 1},
                approval={"poll_interval_seconds": 1, "timeout_seconds": 1},
                rogue_key="should fail",
            )
```

---

### Phase A10: Verify Workstream A

| # | Check | Command |
|---|-------|---------|
| A10.1 | All tests pass | `pytest tests/ -v` |
| A10.2 | No linter errors | Check with IDE/linter |
| A10.3 | Compliance checker works | `python scripts/compliance_checker.py --verbose` |
| A10.4 | No `config.get(` in agent/coordinator code | `rg "config\.get\(" modules/backend/agents/coordinator/` should return empty |
| A10.5 | No `config["` dict subscripts in agent code | `rg 'config\["' modules/backend/agents/` should return empty |
| A10.6 | Schema covers all YAML fields | Manually verify each YAML key has a schema field |
| A10.7 | `extra="forbid"` active | The `test_rejects_unknown_field` tests verify this |

**Commit:** `git commit -m "Add Pydantic schemas for agent and coordinator configs (#3/#4)"`

---

## Workstream B: cli.py Split into Submodules

### Phase B1: Create Module Structure

**Create directory and placeholder files:**

```
modules/backend/cli/
├── __init__.py
├── helpers.py
├── server.py
├── worker.py
├── scheduler.py
├── telegram.py
├── health.py
├── config_display.py
├── testing.py
├── migrate.py
└── info.py
```

Each file starts with a docstring and the standard imports it will need. All files are placeholders at this point — we copy functions one-by-one next.

`modules/backend/cli/__init__.py`:

```python
"""CLI command implementations for the BFF application."""
```

---

### Phase B2: Extract Helpers

**Create `modules/backend/cli/helpers.py`**

Copy these 4 functions verbatim from `cli.py`:

- `_find_process_on_port(port: int) -> list[int]` (lines 34-41)
- `_service_stop(logger, service: str, port: int) -> None` (lines 44-55)
- `_service_status(logger, service: str, port: int) -> None` (lines 58-64)
- `_get_service_port(port: int | None) -> int` (lines 67-72)

Add required imports:

```python
import os
import signal
import subprocess

import click
```

---

### Phase B3: Extract Service Handlers (one by one)

Each file gets the function copied verbatim from the backup, plus its own imports. **Do one file at a time and run tests after each.**

#### B3.1 — `modules/backend/cli/server.py`

Copy `run_server(logger, host, port, reload)` (cli.py lines 241-282).

Imports needed:

```python
import subprocess
import sys

import click

from modules.backend.core.config import get_app_config
```

#### B3.2 — `modules/backend/cli/worker.py`

Copy `run_worker(logger, workers)` (cli.py lines 285-317).

Imports needed:

```python
import subprocess
import sys

import click

from modules.backend.core.config import get_redis_url
```

#### B3.3 — `modules/backend/cli/scheduler.py`

Copy `run_scheduler(logger)` (cli.py lines 320-370).

Imports needed:

```python
import subprocess
import sys

import click

from modules.backend.core.config import get_redis_url
from modules.backend.tasks.scheduled import SCHEDULED_TASKS, register_scheduled_tasks
```

Note: The original has conditional imports inside the function body. Move these to top-level module imports. If the import fails (e.g., `register_scheduled_tasks` unavailable), it will fail when the function is called, not at import time. To preserve lazy loading behavior, keep the imports inside the function body.

Decision: Keep the conditional imports inside the function body to match existing pattern.

#### B3.4 — `modules/backend/cli/telegram.py`

Copy `run_telegram_poll(logger)` and `_run_polling(bot, dp, logger)` (cli.py lines 373-420).

Imports needed:

```python
import asyncio
import sys

import click

from modules.backend.core.config import get_app_config
```

Note: `create_bot` and `create_dispatcher` are imported conditionally inside the function body. Keep that pattern.

#### B3.5 — `modules/backend/cli/health.py`

Copy `check_health(logger)` (cli.py lines 423-505).

Imports needed:

```python
import click
```

All other imports are conditional inside the function body. Keep that pattern.

#### B3.6 — `modules/backend/cli/config_display.py`

Copy `show_config(logger)` (cli.py lines 508-547).

Imports needed:

```python
import sys

import click
```

Note: `get_app_config` is imported conditionally. Keep that pattern.

#### B3.7 — `modules/backend/cli/testing.py`

Copy `run_tests(logger, test_type, coverage)` (cli.py lines 550-580).

Imports needed:

```python
import subprocess
import sys

import click
```

#### B3.8 — `modules/backend/cli/migrate.py`

Copy `run_migrations(logger, migrate_action, revision, message)` (cli.py lines 583-640).

Imports needed:

```python
import subprocess
import sys

import click

from modules.backend.core.config import find_project_root
```

#### B3.9 — `modules/backend/cli/info.py`

Copy `show_info(logger)` (cli.py lines 643-701).

Imports needed:

```python
import sys

import click
```

---

### Phase B4: Rewrite cli.py as Thin Entry Point

Replace the body of `cli.py` with imports from `modules.backend.cli.*`. Keep the Click command, options, and dispatch. Remove all function definitions that were extracted.

**New `cli.py` (~120 lines):**

```python
#!/usr/bin/env python3
"""
BFF Application CLI.

Primary entry point for all application operations.
Use --service to select what to run, --action to control lifecycle.

Usage:
    python cli.py --help
    python cli.py --service server --verbose
    python cli.py --service server --action stop
    python cli.py --service health --debug
    python cli.py --service config
    python cli.py --service test --test-type unit
"""

import sys
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.cli.helpers import _get_service_port, _service_status, _service_stop
from modules.backend.cli.config_display import show_config
from modules.backend.cli.health import check_health
from modules.backend.cli.info import show_info
from modules.backend.cli.migrate import run_migrations
from modules.backend.cli.scheduler import run_scheduler
from modules.backend.cli.server import run_server
from modules.backend.cli.telegram import run_telegram_poll
from modules.backend.cli.testing import run_tests
from modules.backend.cli.worker import run_worker
from modules.backend.core.config import validate_project_root
from modules.backend.core.logging import bind_context, get_logger, setup_logging

LONG_RUNNING_SERVICES = frozenset({"server", "worker", "scheduler", "telegram-poll"})


@click.command()
@click.option(
    "--service", "-s",
    type=click.Choice(["server", "worker", "scheduler", "health", "config",
                        "test", "info", "migrate", "telegram-poll"]),
    default="info",
    help="Service or command to run.",
)
# ... all other @click.option decorators stay exactly the same ...
def main(
    service, action, verbose, debug, host, port, reload,
    test_type, coverage, migrate_action, revision, message, workers,
):
    """
    BFF Application CLI.
    ... docstring stays the same ...
    """
    validate_project_root()

    if debug:
        log_level = "DEBUG"
    elif verbose:
        log_level = "INFO"
    else:
        log_level = "WARNING"

    setup_logging(level=log_level, format_type="console")
    bind_context(source="cli")
    logger = get_logger(__name__)
    logger.debug("CLI invoked", extra={"service": service, "action": action, "log_level": log_level})

    if service in LONG_RUNNING_SERVICES and action != "start":
        service_port = _get_service_port(port)
        if action == "stop":
            _service_stop(logger, service, service_port)
            return
        elif action == "status":
            _service_status(logger, service, service_port)
            return
        elif action == "restart":
            _service_stop(logger, service, service_port)
            import time
            time.sleep(2)

    if service == "server":
        run_server(logger, host, port, reload)
    elif service == "worker":
        run_worker(logger, workers)
    elif service == "scheduler":
        run_scheduler(logger)
    elif service == "health":
        check_health(logger)
    elif service == "config":
        show_config(logger)
    elif service == "test":
        run_tests(logger, test_type, coverage)
    elif service == "info":
        show_info(logger)
    elif service == "migrate":
        run_migrations(logger, migrate_action, revision, message)
    elif service == "telegram-poll":
        run_telegram_poll(logger)


if __name__ == "__main__":
    main()
```

**Critical:** Copy all Click `@click.option(...)` decorators exactly as-is. Do not change any option names, types, defaults, or help text.

---

### Phase B5: Verify Workstream B

| # | Check | Command |
|---|-------|---------|
| B5.1 | All tests pass | `pytest tests/ -v` |
| B5.2 | CLI help works | `python cli.py --help` |
| B5.3 | Server starts | `python cli.py --service server --verbose` (Ctrl+C to stop) |
| B5.4 | Health check works | `python cli.py --service health --verbose` |
| B5.5 | Config display works | `python cli.py --service config` |
| B5.6 | Info display works | `python cli.py --service info` |
| B5.7 | Test suite runs | `python cli.py --service test --test-type unit` |
| B5.8 | No function left in cli.py | Verify cli.py contains only imports, constants, Click command, and dispatch |
| B5.9 | All functions accounted for | Verify every original function exists in exactly one submodule |
| B5.10 | No linter errors | Check with IDE/linter |
| B5.11 | cli.py under 200 lines | `wc -l cli.py` |
| B5.12 | Each submodule under 100 lines | `wc -l modules/backend/cli/*.py` |

**Commit:** `git commit -m "Split cli.py into submodules — 706 lines to ~120 entry point (#14)"`

---

## Phase 10: Final Verification

| # | Check | Command |
|---|-------|---------|
| 10.1 | Full test suite passes | `pytest tests/ -v` (all 416+ tests) |
| 10.2 | Compliance checker works | `python scripts/compliance_checker.py --verbose` |
| 10.3 | Zero linter errors | IDE/linter check |
| 10.4 | No raw `yaml.safe_load` in agent code | `rg "yaml.safe_load" modules/backend/agents/` — only in registry.py (before schema validation) |
| 10.5 | No dict subscript config access | `rg 'config\[' modules/backend/agents/` — empty |
| 10.6 | cli.py is thin entry point | Under 200 lines, no function definitions except `main()` |
| 10.7 | All submodules have docstrings | Check each file in `modules/backend/cli/` |

---

## Files Created

| File | Purpose | Est. Lines |
|------|---------|-----------|
| `modules/backend/agents/config_schema.py` | Pydantic schemas for agent + coordinator YAML | ~120 |
| `modules/backend/cli/__init__.py` | Package init | ~3 |
| `modules/backend/cli/helpers.py` | Shared CLI helper functions | ~45 |
| `modules/backend/cli/server.py` | `--service server` handler | ~55 |
| `modules/backend/cli/worker.py` | `--service worker` handler | ~45 |
| `modules/backend/cli/scheduler.py` | `--service scheduler` handler | ~65 |
| `modules/backend/cli/telegram.py` | `--service telegram-poll` handler | ~55 |
| `modules/backend/cli/health.py` | `--service health` handler | ~95 |
| `modules/backend/cli/config_display.py` | `--service config` handler | ~50 |
| `modules/backend/cli/testing.py` | `--service test` handler | ~45 |
| `modules/backend/cli/migrate.py` | `--service migrate` handler | ~70 |
| `modules/backend/cli/info.py` | `--service info` handler | ~70 |
| `tests/unit/backend/agents/test_config_schema.py` | Schema validation tests | ~100 |

## Files Modified

| File | Change |
|------|--------|
| `modules/backend/agents/coordinator/registry.py` | Validate YAML → `AgentConfigSchema`, typed access |
| `modules/backend/agents/coordinator/middleware.py` | Validate YAML → `CoordinatorConfigSchema`, typed access |
| `modules/backend/agents/coordinator/coordinator.py` | Accept schema types, typed access |
| `modules/backend/agents/deps/base.py` | `config: AgentConfigSchema \| None` |
| `modules/backend/agents/vertical/code/qa/agent.py` | Attribute access instead of dict subscripts |
| `modules/backend/agents/vertical/system/health/agent.py` | Attribute access instead of dict subscripts |
| `modules/backend/agents/tools/compliance.py` | Accept `AgentConfigSchema`, `.model_dump()` at service boundary |
| `scripts/compliance_checker.py` | `.model_dump()` when passing to service |
| `cli.py` | Strip to thin entry point (~120 lines) |
| `tests/unit/backend/agents/test_coordinator.py` | Update assertions for schema types |
| `tests/unit/backend/agents/test_agent_testmodel.py` | Verify fixtures still work (may need no changes) |

---

## Remaining QA Audit Items After This Plan

| # | Finding | Status After |
|---|---------|-------------|
| 3 | Raw yaml.safe_load without Pydantic validation | **Fixed** |
| 4 | Guardrails dict subscript fails at runtime | **Fixed** (typed access) |
| 14 | cli.py 706 lines | **Fixed** (~120 lines) |
| 2 | API key injection pattern | Still open |
| 7/21 | USER_ROLES hardcoded | Still open |
| 8 | Global mutable singletons | Still open |
| 11 | Mock-heavy tests | Still open |
| 16 | Repository test coverage | Still open |
| 20 | dead_code_detector rewrite | Still open |
