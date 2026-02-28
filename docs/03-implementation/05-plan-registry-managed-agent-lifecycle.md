# Implementation Plan: Registry-Managed Agent Lifecycle

*Created: 2026-02-26*
*Status: Pending*
*Branch: `feature/registry-agent-lifecycle`*
*Fixes: QA audit finding #8 (global mutable singletons)*
*Reference: docs 40, 41, 47*

---

## Summary

Move agent instance caching from module-level `_agent` globals to the `AgentRegistry`. Agent modules become pure factory functions (`create_agent()`) with zero mutable state. The registry manages instance lifecycle with lazy creation and a public `reset()` API for tests. Tests stop poking at module internals (`qa_mod._agent = None`) and use `registry.reset()` instead.

**What changes:**
- Agent modules: `_agent` global + `_get_agent()` → `create_agent()` factory function
- Registry: adds `_instances` cache, `get_instance()`, `reset()`
- Coordinator: gets agent from registry, passes to `run_agent()`
- Tests: `registry.reset()` replaces manual singleton clearing

**What does NOT change:**
- `@lru_cache` on `get_registry()`, `_load_coordinator_config()`, `get_settings()`, `get_app_config()` — read-only config caches, correct pattern
- Database engine singleton in `database.py` — correct for connection pools
- Agent module public interface: `run_agent()`, `run_agent_stream()`, `create_agent()` (replaces `_get_agent()`)

---

## Phase 0: Git Safety

| # | Task |
|---|------|
| 0.1 | Commit any uncommitted work |
| 0.2 | Create branch `feature/registry-agent-lifecycle` |
| 0.3 | Backup files to `_backups/` |

**Backup list:**

```
_backups/
├── registry.py             ← modules/backend/agents/coordinator/registry.py
├── coordinator.py          ← modules/backend/agents/coordinator/coordinator.py
├── qa_agent.py             ← modules/backend/agents/vertical/code/qa/agent.py
├── health_agent.py         ← modules/backend/agents/vertical/system/health/agent.py
└── test_agent_testmodel.py ← tests/unit/backend/agents/test_agent_testmodel.py
```

---

## Phase 1: Add Instance Cache to AgentRegistry

**Modify `modules/backend/agents/coordinator/registry.py`**

Add a second cache (`_instances`) alongside the existing config cache (`_agents`). The registry already manages configs — this extends it to also manage the PydanticAI `Agent` objects those configs produce.

### 1.1 Add `_instances` dict to `__init__`

```python
# BEFORE
def __init__(self) -> None:
    self._agents: dict[str, AgentConfigSchema] = {}
    self._loaded = False

# AFTER
def __init__(self) -> None:
    self._agents: dict[str, AgentConfigSchema] = {}
    self._instances: dict[str, Any] = {}
    self._loaded = False
```

### 1.2 Add `get_instance()` method

This is the core addition. Lazy creation: first call imports the agent module, calls `create_agent()`, caches the result. Subsequent calls return the cached instance.

```python
def get_instance(self, agent_name: str, model: Any) -> Any:
    """Get or create a cached PydanticAI Agent instance.

    First call imports the agent module and calls its create_agent() factory.
    Subsequent calls return the cached instance. Call reset() to clear.
    """
    if agent_name in self._instances:
        return self._instances[agent_name]

    module_path = self.resolve_module_path(agent_name)
    module = importlib.import_module(module_path)
    agent = module.create_agent(model)
    self._instances[agent_name] = agent

    logger.info(
        "Agent instance created",
        extra={"agent_name": agent_name},
    )
    return agent
```

Add `import importlib` to the top of the file.

### 1.3 Add `reset()` method

Public API for tests. Clears all cached agent instances so the next `get_instance()` call creates fresh ones (e.g., with `TestModel`).

```python
def reset(self) -> None:
    """Clear all cached agent instances.

    Call this in test fixtures to allow TestModel injection.
    Config cache (_agents) is not affected.
    """
    self._instances.clear()
```

---

## Phase 2: Convert QA Agent to Factory Function

**Modify `modules/backend/agents/vertical/code/qa/agent.py`**

Remove the module-level `_agent` global and `_get_agent()`. Replace with a `create_agent()` factory function that has zero side effects — it creates and returns a fresh agent instance.

### 2.1 Delete module-level global

```python
# DELETE these lines (current lines 23, and the global keyword in _get_agent)
_agent: Agent[QaAgentDeps, QaAuditResult] | None = None
```

### 2.2 Rename `_get_agent()` to `create_agent()`, remove caching

```python
# BEFORE
def _get_agent(model: str | Model) -> Agent[QaAgentDeps, QaAuditResult]:
    """Lazy initialization — creates the agent on first call."""
    global _agent
    if _agent is not None:
        return _agent
    ...
    _agent = agent
    logger.info("QA compliance agent initialized", extra={"model": model})
    return _agent

# AFTER
def create_agent(model: str | Model) -> Agent[QaAgentDeps, QaAuditResult]:
    """Factory: create a QA compliance agent with all tools registered.

    Called by AgentRegistry.get_instance() on first use.
    The registry caches the result — this function is not called again
    unless registry.reset() is called.
    """
    instructions = assemble_instructions("code", "qa")

    agent = Agent(
        model,
        deps_type=QaAgentDeps,
        output_type=QaAuditResult,
        instructions=instructions,
    )

    # ... all @agent.tool registrations stay exactly the same ...

    logger.info("QA compliance agent created", extra={"model": str(model)})
    return agent
```

### 2.3 Update `run_agent()` — receive agent instance as parameter

```python
# BEFORE
async def run_agent(
    user_message: str,
    deps: QaAgentDeps,
    usage_limits: UsageLimits | None = None,
    model: str | Model | None = None,
) -> QaAuditResult:
    """Standard agent entry point. Called by the coordinator."""
    resolved_model = model or deps.config.model
    agent = _get_agent(resolved_model)
    ...

# AFTER
async def run_agent(
    user_message: str,
    deps: QaAgentDeps,
    agent: Agent[QaAgentDeps, QaAuditResult],
    usage_limits: UsageLimits | None = None,
) -> QaAuditResult:
    """Standard agent entry point. Called by the coordinator.

    The agent instance is provided by the coordinator (from the registry).
    This function handles execution, logging, and result extraction.
    """
    logger.info("QA agent invoked", extra={"message": user_message})
    result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)

    logger.info(
        "QA agent completed",
        extra={
            "summary": result.output.summary,
            "total_violations": result.output.total_violations,
            "fixed_count": result.output.fixed_count,
            "usage": {
                "requests": result.usage().requests,
                "input_tokens": result.usage().input_tokens,
                "output_tokens": result.usage().output_tokens,
            },
        },
    )
    return result.output
```

### 2.4 Update `run_agent_stream()` — receive agent instance as parameter

```python
# BEFORE
async def run_agent_stream(
    user_message: str,
    deps: QaAgentDeps,
    conversation_id: str | None = None,
    usage_limits: UsageLimits | None = None,
    model: str | Model | None = None,
) -> AsyncGenerator[dict, None]:
    ...
    async def _run():
        resolved_model = model or deps.config.model
        agent = _get_agent(resolved_model)
        ...

# AFTER
async def run_agent_stream(
    user_message: str,
    deps: QaAgentDeps,
    agent: Agent[QaAgentDeps, QaAuditResult],
    conversation_id: str | None = None,
    usage_limits: UsageLimits | None = None,
) -> AsyncGenerator[dict, None]:
    ...
    async def _run():
        logger.info("QA agent invoked (stream)", ...)
        result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)
        return result.output
```

Remove `from pydantic_ai.models import Model` import if no longer used.

---

## Phase 3: Convert Health Agent to Factory Function

**Modify `modules/backend/agents/vertical/system/health/agent.py`**

Exact same pattern as Phase 2.

### 3.1 Delete module-level `_agent` global

### 3.2 Rename `_get_agent()` to `create_agent()`, remove caching

```python
def create_agent(model: str | Model) -> Agent[HealthAgentDeps, HealthCheckResult]:
    """Factory: create a health agent with all tools registered."""
    instructions = assemble_instructions("system", "health")

    agent = Agent(
        model,
        deps_type=HealthAgentDeps,
        output_type=HealthCheckResult,
        instructions=instructions,
    )

    @agent.tool
    async def check_system_health(ctx: RunContext[HealthAgentDeps]) -> dict:
        ...

    @agent.tool
    async def get_app_info(ctx: RunContext[HealthAgentDeps]) -> dict:
        ...

    logger.info("Health agent created", extra={"model": str(model)})
    return agent
```

### 3.3 Update `run_agent()` — receive agent instance

```python
async def run_agent(
    user_message: str,
    deps: HealthAgentDeps,
    agent: Agent[HealthAgentDeps, HealthCheckResult],
    usage_limits: UsageLimits | None = None,
) -> HealthCheckResult:
```

### 3.4 Update `run_agent_stream()` — receive agent instance

```python
async def run_agent_stream(
    user_message: str,
    deps: HealthAgentDeps,
    agent: Agent[HealthAgentDeps, HealthCheckResult],
    conversation_id: str | None = None,
    usage_limits: UsageLimits | None = None,
) -> AsyncGenerator[dict, None]:
    result = await run_agent(user_message, deps, agent, usage_limits)
    yield {...}
```

---

## Phase 4: Update Coordinator to Use Registry Instances

**Modify `modules/backend/agents/coordinator/coordinator.py`**

The coordinator currently imports agent modules and calls `module.run_agent(..., model=model)`. Change it to get the agent instance from the registry and pass it to `module.run_agent(..., agent=agent)`.

### 4.1 Update `_execute_agent()`

```python
# BEFORE
async def _execute_agent(agent_name, user_input, agent_config):
    model = _build_model(agent_config.model)
    module = _import_agent_module(agent_name)
    deps = _build_agent_deps(agent_name, agent_config)
    limits = _get_usage_limits()
    result = await module.run_agent(user_input, deps, usage_limits=limits, model=model)
    ...

# AFTER
async def _execute_agent(agent_name, user_input, agent_config):
    registry = get_registry()
    model = _build_model(agent_config.model)
    agent = registry.get_instance(agent_name, model)
    module = _import_agent_module(agent_name)
    deps = _build_agent_deps(agent_name, agent_config)
    limits = _get_usage_limits()
    result = await module.run_agent(user_input, deps, agent, usage_limits=limits)
    ...
```

### 4.2 Update `handle_direct_stream()`

```python
# BEFORE
agent_config = registry.get(agent_name)
model = _build_model(agent_config.model)
module = _import_agent_module(agent_name)

if hasattr(module, "run_agent_stream"):
    deps = _build_agent_deps(agent_name, agent_config)
    limits = _get_usage_limits()
    async for event in module.run_agent_stream(
        user_input, deps, conversation_id=conversation_id,
        usage_limits=limits, model=model,
    ):
        yield event

# AFTER
agent_config = registry.get(agent_name)
model = _build_model(agent_config.model)
agent = registry.get_instance(agent_name, model)
module = _import_agent_module(agent_name)

if hasattr(module, "run_agent_stream"):
    deps = _build_agent_deps(agent_name, agent_config)
    limits = _get_usage_limits()
    async for event in module.run_agent_stream(
        user_input, deps, agent,
        conversation_id=conversation_id, usage_limits=limits,
    ):
        yield event
```

---

## Phase 5: Update Tests

**Modify `tests/unit/backend/agents/test_agent_testmodel.py`**

### 5.1 Replace `_reset_agent_singletons` fixture

```python
# BEFORE
@pytest.fixture(autouse=True)
def _reset_agent_singletons():
    """Reset agent singletons before each test so TestModel can be injected."""
    import modules.backend.agents.vertical.code.qa.agent as qa_mod
    import modules.backend.agents.vertical.system.health.agent as health_mod

    qa_mod._agent = None
    health_mod._agent = None
    yield
    qa_mod._agent = None
    health_mod._agent = None

# AFTER
@pytest.fixture(autouse=True)
def _reset_agent_instances():
    """Clear registry agent cache before each test so TestModel can be used."""
    from modules.backend.agents.coordinator.registry import get_registry

    get_registry().reset()
    yield
    get_registry().reset()
```

### 5.2 Update test methods — use `create_agent()` instead of `_get_agent()`

```python
# BEFORE
class TestQaAgentWithTestModel:

    @pytest.mark.asyncio
    async def test_returns_qa_audit_result_schema(self, qa_deps):
        from modules.backend.agents.vertical.code.qa.agent import _get_agent

        agent = _get_agent(TestModel(call_tools=[]))
        result = await agent.run("run compliance audit", deps=qa_deps)
        assert isinstance(result.output, QaAuditResult)
        ...

# AFTER
class TestQaAgentWithTestModel:

    @pytest.mark.asyncio
    async def test_returns_qa_audit_result_schema(self, qa_deps):
        from modules.backend.agents.vertical.code.qa.agent import create_agent

        agent = create_agent(TestModel(call_tools=[]))
        result = await agent.run("run compliance audit", deps=qa_deps)
        assert isinstance(result.output, QaAuditResult)
        ...
```

Apply the same change to all test methods in both `TestQaAgentWithTestModel` and `TestHealthAgentWithTestModel`:
- Replace `_get_agent` import with `create_agent` import
- Replace `_get_agent(TestModel(...))` with `create_agent(TestModel(...))`
- Remove all `qa_mod._agent = None` / `health_mod._agent = None` lines inside test methods

### 5.3 Update `test_run_agent_interface` tests

These tests call `run_agent()` through the module's public interface. Since `run_agent()` now takes an `agent` parameter:

```python
# BEFORE
@pytest.mark.asyncio
async def test_run_agent_interface(self, qa_deps):
    import modules.backend.agents.vertical.code.qa.agent as qa_mod
    qa_mod._agent = None

    from modules.backend.agents.vertical.code.qa.agent import _get_agent
    _get_agent(TestModel(call_tools=[]))

    from modules.backend.agents.vertical.code.qa.agent import run_agent
    result = await run_agent("scan everything", qa_deps)
    assert isinstance(result, QaAuditResult)

# AFTER
@pytest.mark.asyncio
async def test_run_agent_interface(self, qa_deps):
    from modules.backend.agents.vertical.code.qa.agent import create_agent, run_agent

    agent = create_agent(TestModel(call_tools=[]))
    result = await run_agent("scan everything", qa_deps, agent)
    assert isinstance(result, QaAuditResult)
```

Same pattern for health agent `test_run_agent_interface`.

### 5.4 Add registry reset test

Add a test to `TestAgentRegistry` in `test_coordinator.py`:

```python
def test_reset_clears_instances(self):
    """registry.reset() clears cached agent instances."""
    registry = get_registry()
    registry._instances["fake.agent"] = "sentinel"
    assert "fake.agent" in registry._instances

    registry.reset()
    assert "fake.agent" not in registry._instances
```

---

## Phase 6: Verify

| # | Check | Command |
|---|-------|---------|
| 6.1 | All tests pass | `pytest tests/ -v` |
| 6.2 | No `_agent` globals in agent modules | `rg "^_agent" modules/backend/agents/vertical/` — empty |
| 6.3 | No `global _agent` in agent modules | `rg "global _agent" modules/backend/agents/` — empty |
| 6.4 | No `_agent = None` in test files | `rg "_agent = None" tests/` — empty |
| 6.5 | No `_get_agent` anywhere | `rg "_get_agent" modules/ tests/` — empty |
| 6.6 | Compliance checker works | `python scripts/compliance_checker.py --verbose` |
| 6.7 | No linter errors | IDE/linter check |

**Commit:** `git commit -m "Move agent instances from module globals to registry cache (#8)"`

---

## Files Modified

| File | Change |
|------|--------|
| `modules/backend/agents/coordinator/registry.py` | Add `_instances`, `get_instance()`, `reset()` |
| `modules/backend/agents/coordinator/coordinator.py` | Get agent from registry, pass to `run_agent()` |
| `modules/backend/agents/vertical/code/qa/agent.py` | Delete `_agent` global, `_get_agent()` → `create_agent()`, `run_agent()` takes `agent` param |
| `modules/backend/agents/vertical/system/health/agent.py` | Same as QA agent |
| `tests/unit/backend/agents/test_agent_testmodel.py` | `registry.reset()`, `create_agent()`, pass `agent` to `run_agent()` |
| `tests/unit/backend/agents/test_coordinator.py` | Add `test_reset_clears_instances` |

## Files NOT Modified

| File | Reason |
|------|--------|
| `modules/backend/agents/coordinator/middleware.py` | `@lru_cache` on config is correct — read-only, has `.cache_clear()` |
| `modules/backend/core/config.py` | `@lru_cache` on settings/config is correct |
| `modules/backend/core/database.py` | `_engine` singleton is correct for connection pools |
| `scripts/compliance_checker.py` | Does not use agent instances (uses `ComplianceScannerService` directly) |

---

## Design Rationale

**Why registry-managed, not the three conventional options:**

| Option | Why Not |
|--------|---------|
| Dependency injection (pass Agent through call chain) | Agent is a reusable template, not a per-request dependency. Mismodels the problem. |
| FastAPI lifespan | Couples to FastAPI. Agents are used from CLI and Taskiq too. |
| Factory with explicit reset per module | N modules = N reset functions. Tests still know module internals. |

**Why this approach:**

| Principle | How It's Met |
|-----------|-------------|
| Doc 40: "agents are templates, not singletons" | Factory creates templates. Registry caches them. |
| Doc 41: `agent_router.resolve()` pattern | `registry.get_instance()` resolves agent by name. |
| Doc 47: "lazy initialization" | `get_instance()` creates on first call. |
| Doc 47: "support TestModel overrides" | `registry.reset()` clears cache. Next call uses TestModel. |
| Zero module-level mutable state | Agent modules have no globals. |
| Entry-point agnostic | Works from FastAPI, CLI, Taskiq, tests. |
| Single lifecycle control point | One `reset()` clears all agents. |
