# Implementation Plan: Horizontal PM Agent + Delegation

*Created: 2026-03-02*
*Status: Not Started*
*Phase: 4 of 6 (AI-First Platform Build)*
*Depends on: Phase 1 (Event Bus), Phase 2 (Session Model), Phase 3 (Streaming Coordinator)*
*Blocked by: Phase 3*

---

## Summary

Build the first horizontal agent — a PM (project manager) that decomposes goals into tasks, delegates to vertical agents, monitors progress, and reports results. This proves the agent team pattern: horizontal supervisors delegate to vertical specialists through the coordinator.

Horizontal agents are real PydanticAI agents with their own tools and decision-making capability. They differ from vertical agents in scope (cross-domain, not single-domain), action (delegate, not execute), model (capable models for judgment), and tools (delegation + read-only filesystem, not domain-specific execution tools).

**Dev mode: breaking changes allowed.** This is a new subsystem — no backward-compatibility constraints. The `AgentConfigSchema` gains a `delegation` field. The coordinator's `_build_agent_deps` gains horizontal agent support. All delegation flows through the coordinator's session-based `handle()` from Phase 3.

## Context

- Architecture: `docs/99-reference-architecture/47-agent-module-organization.md` — vertical vs horizontal agent types, delegation tool pattern, access control model, prompt layering, horizontal agent YAML schema
- Architecture: `docs/99-reference-architecture/40-agentic-architecture.md` — Thinker/Specialist/Worker tiers, orchestration patterns
- Architecture: `docs/99-reference-architecture/46-event-session-architecture.md` — session model, streaming coordinator, cost tracking
- `HorizontalAgentDeps` already exists in `modules/backend/agents/deps/base.py` with `allowed_agents`, `max_delegation_depth`, and `coordinator`
- `AgentRegistry.resolve_module_path()` already resolves horizontal agent paths: `modules.backend.agents.horizontal.{name}.agent`
- `coordinator.yaml` already references `horizontal.pm.agent` as `complex_request_agent` and `fallback_agent`
- Phase 3 coordinator `handle()` returns `AsyncIterator[SessionEvent]` with `collect()` for synchronous callers
- Existing agent pattern: `create_agent(model) -> Agent`, `run_agent(message, deps, agent)`, thin tool wrappers over shared implementations in `agents/tools/`

## What to Build

- `modules/backend/agents/config_schema.py` — Add `DelegationSchema` and optional `delegation` field to `AgentConfigSchema`
- `modules/backend/agents/tools/delegation.py` — `invoke_agent()`, `list_available_agents()` shared tool implementations (pure functions, no PydanticAI dependency)
- `modules/backend/agents/horizontal/__init__.py` — package init
- `modules/backend/agents/horizontal/pm/__init__.py` — package init
- `modules/backend/agents/horizontal/pm/agent.py` — PM agent: `create_agent()`, `run_agent()`, `run_agent_stream()`, thin tool wrappers for delegation and filesystem
- `modules/backend/agents/schemas.py` — Add `DelegationResult`, `PmResult` output schemas
- `modules/backend/agents/deps/base.py` — Add `delegation_depth` field to `HorizontalAgentDeps`
- `modules/backend/agents/coordinator/coordinator.py` — Update `_build_agent_deps()` to construct `HorizontalAgentDeps` for horizontal agents, binding the delegation callable
- `config/agents/horizontal/pm/agent.yaml` — PM agent YAML config with delegation allowlist
- `config/prompts/categories/horizontal.md` — Layer 1 prompt: "You supervise. You do not execute."
- `config/prompts/agents/horizontal/pm/system.md` — Layer 2 prompt: PM identity, decomposition workflow, delegation rules
- `tests/unit/backend/agents/tools/test_delegation.py` — Delegation tool unit tests
- `tests/unit/backend/agents/test_pm_agent.py` — PM agent tests with TestModel

## Key Design Decisions

- **PM delegates through the coordinator** — never bypasses it. The `delegation.invoke_agent` tool calls the coordinator's `collect()` (Phase 3) which re-enters the full middleware chain: routing, cost tracking, budget enforcement, event publishing. Cost rolls up to the parent session.
- **Delegation allowlist in YAML** — the PM's `agent.yaml` declares which agents it can invoke. The `invoke_agent` tool checks this before delegating. A delegation to an unlisted agent raises `PermissionError`.
- **`max_delegation_depth` prevents infinite delegation loops** — each delegation increments a depth counter. When `delegation_depth >= max_delegation_depth`, the tool raises `PermissionError`. Depth is tracked in `HorizontalAgentDeps.delegation_depth`.
- **`coordinator` field on `HorizontalAgentDeps`** — a callable `async (agent_name, task) -> dict` that the delegation tool invokes. The coordinator builds this at deps construction time, binding the parent session_id and services. The delegation tool never imports the coordinator directly.
- **PM uses a capable model (Sonnet)** for judgment. Vertical agents use cheaper models (Haiku) for execution. This is the Thinker/Specialist split from doc 40.
- **PM has read-only scope** on `docs/`, `config/`, `logs/`. It cannot write code — it delegates code work to vertical agents like `code.coder.agent` or `code.qa.agent`.
- **PM does NOT have plan tools yet** — `plan.create_plan`, `plan.revise_plan`, `plan.get_status` are defined in Plan 14 (Plan Management). For now, the PM reasons about task decomposition in its system prompt and delegates sequentially.
- **`DelegationSchema` added to config schema** — `AgentConfigSchema` gains an optional `delegation` field. Vertical agents omit it. Horizontal agents include it with `allowed_agents` and `max_delegation_depth`. This is validated at YAML load time.
- **Deterministic fast-path before LLM (P2)** — `run_agent()` includes a pre-processing step that checks if the goal matches a known pattern before invoking the LLM. If a goal maps directly to a single agent delegation (e.g., "run QA on X" → delegate to `code.qa.agent`), or matches a simple sequential pattern, the fast-path builds the delegation plan deterministically and skips LLM reasoning. The LLM is reserved for genuinely ambiguous goals that require judgment. See Step 8 for implementation.

## Success Criteria

- [ ] PM agent receives a goal, decomposes it, delegates subtasks to vertical agents via `invoke_agent` tool
- [ ] Delegation flows through coordinator with full middleware (cost tracking, budget enforcement, event emission)
- [ ] Allowlist enforcement: PM cannot invoke agents not in its config — `PermissionError` raised
- [ ] Delegation depth limit prevents loops — `PermissionError` at `depth >= max_delegation_depth`
- [ ] `list_available_agents` tool shows only agents in the PM's allowlist
- [ ] PM agent returns structured `PmResult` with summary, delegations, and completion status
- [ ] Config schema validates delegation config — missing `allowed_agents` on a horizontal agent is caught at load time
- [ ] Horizontal category prompt applies to all horizontal agents
- [ ] PM system prompt follows the 4-layer architecture (organization → horizontal → pm)
- [ ] End-to-end: PM delegates QA scan to `code.qa.agent`, receives results, reports back
- [ ] All tests use `TestModel` — no real API calls

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/horizontal-pm-agent` |

---

### Step 1: Add `DelegationSchema` to Config Schema

**File**: `modules/backend/agents/config_schema.py`

Add the delegation config schema and extend `AgentConfigSchema` with an optional `delegation` field. This must be done first because the registry validates YAML against this schema when loading agents.

```python
class DelegationSchema(_StrictBase):
    """Delegation authority for horizontal agents."""

    allowed_agents: list[str]
    max_delegation_depth: int = Field(default=2, ge=1, le=10)
```

Then add to `AgentConfigSchema`:

```python
class AgentConfigSchema(_StrictBase):
    # ... existing fields ...

    # Horizontal-agent-specific (optional — vertical agents omit this)
    delegation: DelegationSchema | None = None
```

**Why this order**: The PM's `agent.yaml` includes a `delegation` block. If we create the YAML before updating the schema, the registry will reject it with `extra="forbid"`.

**Verification**: Run existing tests — they must still pass because `delegation` is optional and existing agent YAMLs don't include it.

---

### Step 2: Create PM Agent YAML Config

**File**: `config/agents/horizontal/pm/agent.yaml`

Create the directory structure and YAML config. This follows the exact schema from doc 47 Section "Horizontal Agent YAML":

```yaml
# =============================================================================
# PM (Project Manager) Horizontal Agent Configuration
# =============================================================================
# Available options:
#   agent_name        - Unique agent identifier (string, format: horizontal.name.agent)
#   agent_type        - Agent type (string: horizontal)
#   description       - Agent description for routing (string)
#   enabled           - Enable/disable without code deployment (boolean)
#   model             - LLM model identifier (string, provider:model format)
#   keywords          - Keywords for rule-based routing (list of strings)
#   tools             - Shared tool names (list of dotted strings, domain.action)
#   max_input_length  - Maximum input character count (integer)
#   max_budget_usd    - Maximum cost per invocation in USD (decimal)
#   execution         - Execution mode (object)
#     mode            - Execution environment (string: local | container)
#   scope             - Filesystem access control (object)
#     read            - Paths the agent can read (list of strings)
#     write           - Paths the agent can write (list of strings)
#   delegation        - Delegation configuration (object)
#     allowed_agents  - Agents this horizontal agent can invoke (list of strings)
#     max_delegation_depth - Maximum recursive delegation depth (integer)
# =============================================================================

agent_name: horizontal.pm.agent
agent_type: horizontal
description: "Decomposes goals into tasks, sequences work, delegates to vertical specialists"
enabled: true
model: anthropic:claude-sonnet-4-20250514
max_input_length: 32000
max_budget_usd: 5.00

keywords:
  - plan
  - project
  - decompose
  - coordinate
  - sequence
  - manage
  - organize

tools:
  - delegation.invoke_agent
  - delegation.list_agents
  - filesystem.read_file
  - filesystem.list_files

scope:
  read:
    - "docs/"
    - "config/"
    - "logs/"
  write: []

delegation:
  allowed_agents:
    - code.qa.agent
    - code.coder.agent
    - system.health.agent
  max_delegation_depth: 2

execution:
  mode: local
```

**Decisions**:
- `max_budget_usd: 5.00` — higher than vertical agents ($0.50) because PM orchestrates multiple delegations. Each delegated agent has its own per-invocation budget, but the PM's budget covers its own reasoning cost.
- `allowed_agents` — only agents that currently exist. As more agents are added, update this list. `code.review.agent` and `code.coder.agent` will be added when those agents are implemented.
- `model: anthropic:claude-sonnet-4-20250514` — Sonnet for judgment quality. Horizontal agents need capable reasoning to decompose goals correctly.
- `write: []` — PM never writes files. It delegates write operations to vertical agents.
- Keywords include "plan", "project", "manage" — the coordinator routes complex requests here.

**Verification**: After Step 1, the registry should discover and load this YAML without errors. Run:

```bash
python -c "from modules.backend.agents.coordinator.registry import get_registry; r = get_registry(); print(r.get('horizontal.pm.agent'))"
```

---

### Step 3: Create Horizontal Category Prompt

**File**: `config/prompts/categories/horizontal.md`

This is the Layer 1 prompt that applies to ALL horizontal agents (PM, architect, director, reviewer — when they're added later). It defines the supervisory identity.

```markdown
## Horizontal Agent Standards

You are a supervisory agent. You do not execute tasks directly.

- **Decompose complex requests into discrete tasks** for vertical specialists.
- **Delegate to the most appropriate vertical agent** for each task. Use `list_available_agents` to see what you can delegate to.
- **Monitor progress and reallocate on failure.** If a delegated task fails, decide whether to retry, try a different agent, or report the failure.
- **Make decisions when tasks conflict** or when vertical agents need guidance.
- **You have read-only access to code and documentation.** You never write code, apply fixes, or modify files. You delegate those actions to vertical agents.
- **Report results comprehensively.** Your output should summarize what was done, what succeeded, what failed, and what remains.
- **When uncertain about a decision, report the uncertainty** rather than guessing. Present options and let the human decide.
- **Stay within your delegation allowlist.** You can only invoke agents listed in your configuration. Do not attempt to invoke agents outside your allowlist.
```

**Pattern**: Matches the existing `config/prompts/categories/code.md` and `system.md` — imperative rules, no personality, focused on constraints.

---

### Step 4: Create PM Agent Prompt

**File**: `config/prompts/agents/horizontal/pm/system.md`

Create directory structure: `config/prompts/agents/horizontal/pm/`

This is the Layer 2 prompt — the PM's specific identity and behavioral instructions.

```markdown
## Project Manager Agent

You are a project manager. You receive goals from humans and coordinate vertical specialist agents to achieve them.

### Workflow

1. **Understand the goal.** Read the request carefully. If you need context, use `read_file` to examine relevant documentation or configuration.
2. **Decompose into tasks.** Break the goal into discrete, actionable tasks. Each task should be small enough for a single vertical agent to complete.
3. **Sequence tasks.** Determine which tasks depend on others and which can run independently. Execute dependent tasks in order.
4. **Delegate each task.** Use `invoke_agent` to send each task to the appropriate vertical agent. Provide clear, specific instructions — the agent does not have your full context.
5. **Evaluate results.** Check each delegation result. If a task failed, decide: retry, try a different approach, or report as blocked.
6. **Report back.** Summarize what was accomplished, what failed, and any remaining blockers.

### Delegation Rules

- Always use `list_available_agents` first to see which agents are available to you.
- Provide clear, self-contained task descriptions to delegated agents. Include enough context for the agent to act without additional information.
- Do not delegate more than one complex task to the same agent simultaneously — wait for results before delegating the next task.
- If a delegation fails, include the error in your report. Do not silently retry indefinitely.
- You cannot write code or modify files yourself. If a task requires code changes, delegate to a code agent.

### Reading Files

- Use `read_file` and `list_files` to examine documentation, configuration, and logs.
- Read files to understand context before decomposing tasks — do not guess about project structure.
- Your read scope is limited to `docs/`, `config/`, and `logs/`.
```

**Pattern**: Matches `config/prompts/agents/code/qa/system.md` — workflow section with numbered steps, rules section with constraints.

---

### Step 5: Add `delegation_depth` to `HorizontalAgentDeps`

**File**: `modules/backend/agents/deps/base.py`

Add the `delegation_depth` field to track how deep in the delegation chain we are:

```python
@dataclass
class HorizontalAgentDeps(BaseAgentDeps):
    """Horizontal (supervisory) agent deps — adds delegation authority."""

    allowed_agents: set[str] = field(default_factory=set)
    max_delegation_depth: int = 0
    delegation_depth: int = 0
    coordinator: Any = None
```

**What changed**: Added `delegation_depth: int = 0`. This starts at 0 for the top-level PM invocation and increments with each nested delegation. The delegation tool checks `delegation_depth < max_delegation_depth` before delegating.

**`coordinator` field**: This is a callable `async (agent_name: str, task: str) -> dict` built by the coordinator at deps construction time (Step 9). It binds the parent session_id and services so the delegation tool doesn't need to know about sessions or the coordinator module. Typed as `Any` to avoid circular imports.

---

### Step 6: Create Delegation Tool Implementations

**File**: `modules/backend/agents/tools/delegation.py` (NEW)

Shared tool implementations — pure functions with no PydanticAI dependency. These are the implementations that thin wrappers in `agent.py` call.

```python
"""
Shared delegation tool implementations.

Pure functions with no PydanticAI dependency. Used by horizontal agents
to delegate tasks to vertical agents through the coordinator. The
coordinator callable is injected via HorizontalAgentDeps — these
functions never import the coordinator directly.
"""

from typing import Any, Callable, Awaitable

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


async def invoke_agent(
    agent_name: str,
    task: str,
    coordinator: Callable[[str, str], Awaitable[dict[str, Any]]],
    allowed_agents: set[str],
    delegation_depth: int,
    max_delegation_depth: int,
) -> dict[str, Any]:
    """Invoke a vertical agent through the coordinator.

    Args:
        agent_name: The agent to delegate to (e.g., "code.qa.agent").
        task: Clear, self-contained task description for the agent.
        coordinator: Async callable that executes agent_name with task
                     and returns the result dict. Built by the coordinator
                     at deps construction time.
        allowed_agents: Set of agent names this horizontal agent can invoke.
        delegation_depth: Current depth in the delegation chain (0 = top level).
        max_delegation_depth: Maximum allowed depth.

    Returns:
        Dict with agent result: {"agent_name": str, "output": str, ...}

    Raises:
        PermissionError: If agent_name is not in allowed_agents or
                         delegation depth exceeds the maximum.
    """
    if agent_name not in allowed_agents:
        available = ", ".join(sorted(allowed_agents)) or "none"
        raise PermissionError(
            f"Not authorized to delegate to '{agent_name}'. "
            f"Allowed agents: {available}"
        )

    if delegation_depth >= max_delegation_depth:
        raise PermissionError(
            f"Max delegation depth ({max_delegation_depth}) exceeded. "
            f"Current depth: {delegation_depth}"
        )

    logger.info(
        "Delegating to agent",
        extra={
            "target_agent": agent_name,
            "task": task[:200],
            "delegation_depth": delegation_depth,
        },
    )

    result = await coordinator(agent_name, task)

    logger.info(
        "Delegation completed",
        extra={
            "target_agent": agent_name,
            "success": "error" not in str(result.get("output", "")).lower(),
            "delegation_depth": delegation_depth,
        },
    )

    return result


async def list_available_agents(
    allowed_agents: set[str],
    registry_list: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """List agents this horizontal agent is allowed to delegate to.

    Filters the full registry list to only include agents in the
    horizontal agent's allowlist.

    Args:
        allowed_agents: Set of agent names from the delegation config.
        registry_list: Full registry listing from AgentRegistry.list_all().

    Returns:
        List of agent info dicts for allowed agents only.
    """
    return [
        agent for agent in registry_list
        if agent["agent_name"] in allowed_agents
    ]
```

**Design decisions**:
- `invoke_agent` receives the coordinator callable, not the coordinator module — avoids circular imports and keeps the tool pure.
- Depth check happens BEFORE calling the coordinator — fail fast.
- Allowlist check happens BEFORE calling the coordinator — fail fast.
- Task is truncated to 200 chars in logs to avoid log bloat.
- `list_available_agents` takes the pre-fetched registry list, not the registry itself — pure function, no side effects.

---

### Step 7: Add PM Output Schema

**File**: `modules/backend/agents/schemas.py`

Add output schemas for the PM agent. These are the structured output types that PydanticAI validates against.

Add to the existing file:

```python
class DelegationResult(BaseModel):
    """Result from a single delegated task."""

    agent_name: str
    task: str
    success: bool
    output: str
    error: str | None = None


class PmResult(BaseModel):
    """Structured output from the PM agent."""

    summary: str
    goal: str
    delegations: list[DelegationResult]
    completed: bool
    blockers: list[str] = Field(default_factory=list)
```

**Why these fields**:
- `summary` — human-readable summary of what was accomplished (consistent with other agents' outputs)
- `goal` — the original goal the PM was given
- `delegations` — list of all delegation results (what was delegated, to whom, success/failure, output)
- `completed` — whether the overall goal was fully achieved
- `blockers` — any remaining issues that prevented completion

---

### Step 8: Create PM Agent

**File**: `modules/backend/agents/horizontal/pm/agent.py` (NEW)

Create directory structure first:
```
modules/backend/agents/horizontal/__init__.py  (empty)
modules/backend/agents/horizontal/pm/__init__.py  (empty)
```

Then create the agent file following the exact pattern of existing agents (QA agent, health agent):

```python
"""
PM Horizontal Agent (horizontal.pm.agent).

Supervisory agent that decomposes goals into tasks and delegates to
vertical specialist agents through the coordinator. Has read-only
access to docs/config/logs and delegation authority over its allowlist.

All delegation logic lives in agents/tools/delegation.py. All
filesystem logic lives in agents/tools/filesystem.py. This file
registers tools, receives config from the coordinator, and exposes
the standard create_agent() / run_agent() / run_agent_stream() interface.
"""

from collections.abc import AsyncGenerator

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.models import Model

from modules.backend.agents.coordinator.coordinator import assemble_instructions
from modules.backend.agents.coordinator.registry import get_registry
from modules.backend.agents.deps.base import HorizontalAgentDeps
from modules.backend.agents.schemas import DelegationResult, PmResult
from modules.backend.agents.tools import delegation, filesystem
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


# ---- Deterministic fast-path (P2) ----
# Before invoking the LLM, check if the goal matches a known pattern
# that can be resolved deterministically. This is faster, cheaper,
# and more reliable than asking the LLM for trivial decompositions.

SINGLE_AGENT_PATTERNS: dict[str, str] = {
    # keyword prefix -> agent name
    # These match goals that clearly target a single vertical agent.
    # The match is case-insensitive prefix on the first phrase.
    "run qa": "code.qa.agent",
    "audit": "code.qa.agent",
    "compliance scan": "code.qa.agent",
    "check health": "system.health.agent",
    "health check": "system.health.agent",
    "system status": "system.health.agent",
}


def try_fast_path(
    goal: str, allowed_agents: set[str],
) -> PmResult | None:
    """Attempt deterministic decomposition without LLM.

    Returns a PmResult if the goal matches a known pattern,
    None if the goal requires LLM reasoning.
    """
    normalized = goal.strip().lower()

    for prefix, agent_name in SINGLE_AGENT_PATTERNS.items():
        if normalized.startswith(prefix) and agent_name in allowed_agents:
            logger.info(
                "Fast-path match",
                extra={"pattern": prefix, "agent": agent_name},
            )
            return None  # Signal: use fast delegation path

    return None  # No match — fall through to LLM


async def execute_fast_path(
    goal: str,
    deps: HorizontalAgentDeps,
) -> PmResult | None:
    """Execute a deterministic single-agent delegation.

    Returns PmResult if fast-path matched, None otherwise.
    """
    normalized = goal.strip().lower()

    for prefix, agent_name in SINGLE_AGENT_PATTERNS.items():
        if normalized.startswith(prefix) and agent_name in deps.allowed_agents:
            result = await delegation.invoke_agent(
                agent_name=agent_name,
                task=goal,
                coordinator=deps.coordinator,
                allowed_agents=deps.allowed_agents,
                delegation_depth=deps.delegation_depth,
                max_delegation_depth=deps.max_delegation_depth,
            )
            return PmResult(
                summary=f"Delegated to {agent_name} (fast-path)",
                delegations=[DelegationResult(
                    agent_name=agent_name,
                    task=goal,
                    success=result.get("success", True),
                    output=result.get("output", ""),
                )],
                completed=result.get("success", True),
            )

    return None


def create_agent(model: str | Model) -> Agent[HorizontalAgentDeps, PmResult]:
    """Factory: create a PM agent with all tools registered.

    Called by AgentRegistry.get_instance() on first use.
    The registry caches the result — this function is not called again
    unless registry.reset() is called.
    """

    instructions = assemble_instructions("horizontal", "pm")

    agent = Agent(
        model,
        deps_type=HorizontalAgentDeps,
        output_type=PmResult,
        instructions=instructions,
    )

    # ---- Delegation tools (thin wrappers) ----

    @agent.tool
    async def invoke_agent(
        ctx: RunContext[HorizontalAgentDeps],
        agent_name: str,
        task: str,
    ) -> dict:
        """Delegate a task to a vertical agent. The agent must be in your allowlist."""
        return await delegation.invoke_agent(
            agent_name=agent_name,
            task=task,
            coordinator=ctx.deps.coordinator,
            allowed_agents=ctx.deps.allowed_agents,
            delegation_depth=ctx.deps.delegation_depth,
            max_delegation_depth=ctx.deps.max_delegation_depth,
        )

    @agent.tool
    async def list_available_agents(
        ctx: RunContext[HorizontalAgentDeps],
    ) -> list[dict]:
        """List the agents you can delegate to, with their descriptions."""
        from modules.backend.agents.coordinator.registry import get_registry
        registry_list = get_registry().list_all()
        return await delegation.list_available_agents(
            allowed_agents=ctx.deps.allowed_agents,
            registry_list=registry_list,
        )

    # ---- Filesystem tools (thin wrappers — read only) ----

    @agent.tool
    async def read_file(
        ctx: RunContext[HorizontalAgentDeps],
        file_path: str,
    ) -> str:
        """Read a file within your read scope (docs/, config/, logs/)."""
        return await filesystem.read_file(
            ctx.deps.project_root, file_path, ctx.deps.scope,
        )

    @agent.tool
    async def list_files(ctx: RunContext[HorizontalAgentDeps]) -> list[str]:
        """List all Python files in your read scope."""
        return await filesystem.list_files(
            ctx.deps.project_root, ctx.deps.scope,
        )

    logger.info("PM agent created", extra={"model": str(model)})
    return agent


async def run_agent(
    user_message: str,
    deps: HorizontalAgentDeps,
    agent: Agent[HorizontalAgentDeps, PmResult],
    usage_limits: UsageLimits | None = None,
) -> PmResult:
    """Standard agent entry point. Called by the coordinator.

    Tries deterministic fast-path first (P2). Only invokes the LLM
    when the goal requires genuine reasoning and judgment.
    """

    logger.info("PM agent invoked", extra={"message": user_message[:200]})

    # P2: Deterministic fast-path — skip LLM for known patterns
    fast_result = await execute_fast_path(user_message, deps)
    if fast_result is not None:
        logger.info(
            "PM fast-path completed",
            extra={"delegations": len(fast_result.delegations)},
        )
        return fast_result

    # LLM path — goal requires reasoning/judgment
    result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)

    logger.info(
        "PM agent completed",
        extra={
            "summary": result.output.summary,
            "delegations": len(result.output.delegations),
            "completed": result.output.completed,
            "usage": {
                "requests": result.usage().requests,
                "input_tokens": result.usage().input_tokens,
                "output_tokens": result.usage().output_tokens,
            },
        },
    )
    return result.output


async def run_agent_stream(
    user_message: str,
    deps: HorizontalAgentDeps,
    agent: Agent[HorizontalAgentDeps, PmResult],
    conversation_id: str | None = None,
    usage_limits: UsageLimits | None = None,
) -> AsyncGenerator[dict, None]:
    """Standard streaming entry point. Called by the coordinator.

    After Phase 3, streaming goes through the coordinator's event
    system. This is kept for interface compatibility with the
    agent executor pattern.
    """
    result = await run_agent(user_message, deps, agent, usage_limits=usage_limits)
    yield {
        "type": "complete",
        "result": result.model_dump(),
        "conversation_id": conversation_id,
    }
```

**Pattern notes**:
- Follows the exact same structure as `vertical/system/health/agent.py` — `create_agent()`, `run_agent()`, `run_agent_stream()`
- Tool wrappers are thin (2-5 lines) — all logic in `agents/tools/delegation.py` and `agents/tools/filesystem.py`
- `list_available_agents` does a lazy import of the registry to avoid circular imports at module level
- `run_agent_stream` delegates to `run_agent` like the health agent — after Phase 3, the coordinator handles streaming directly

---

### Step 9: Update Coordinator to Build Horizontal Deps

**File**: `modules/backend/agents/coordinator/coordinator.py`

Update `_build_agent_deps()` to detect horizontal agents and construct `HorizontalAgentDeps` with the delegation callable.

**Add import**:
```python
from modules.backend.agents.deps.base import (
    BaseAgentDeps,
    FileScope,
    HealthAgentDeps,
    HorizontalAgentDeps,  # ADD THIS
    QaAgentDeps,
)
```

**Replace `_build_agent_deps` with**:

```python
def _build_agent_deps(
    agent_name: str,
    agent_config: AgentConfigSchema,
    delegation_depth: int = 0,
    session_id: str | None = None,
    session_service: Any = None,
    event_bus: Any = None,
) -> BaseAgentDeps:
    """Build the appropriate deps dataclass for a given agent.

    For horizontal agents, constructs HorizontalAgentDeps with a
    delegation callable that re-enters the coordinator with depth+1.
    """
    common = build_deps_from_config(agent_config)
    category = agent_name.split(".")[0]

    # Horizontal agents get delegation authority
    if agent_config.agent_type == "horizontal" and agent_config.delegation:
        async def _delegate(target_agent: str, task: str) -> dict[str, Any]:
            """Delegation callable — re-enters the coordinator."""
            # After Phase 3, this calls the session-based handle() + collect()
            result = await _execute_agent(
                target_agent,
                task,
                get_registry().get(target_agent),
            )
            return result

        return HorizontalAgentDeps(
            **common,
            allowed_agents=set(agent_config.delegation.allowed_agents),
            max_delegation_depth=agent_config.delegation.max_delegation_depth,
            delegation_depth=delegation_depth,
            coordinator=_delegate,
        )

    if category == "system" and "health" in agent_name:
        return HealthAgentDeps(**common, app_config=get_app_config())
    if category == "code" and "qa" in agent_name:
        return QaAgentDeps(**common)

    return BaseAgentDeps(**common)
```

**Important**: The `_delegate` closure captures the coordinator's internal `_execute_agent` function. This is intentional — delegation re-enters the execution chain with middleware applied. After Phase 3 is implemented, this closure should use the session-based `handle()` + `collect()` instead, passing the parent `session_id` so cost rolls up to the parent session.

**Phase 3 integration note**: When Phase 3 (streaming coordinator) is already in place at the time this is implemented, the `_delegate` function should instead be:

```python
async def _delegate(target_agent: str, task: str) -> dict[str, Any]:
    """Re-enter coordinator with parent session for cost rollup."""
    from modules.backend.agents.coordinator.coordinator import handle, collect
    events = handle(
        session_id=session_id,
        message=task,
        agent=target_agent,
        session_service=session_service,
        event_bus=event_bus,
        delegation_depth=delegation_depth + 1,
    )
    return await collect(events)
```

Use whichever version matches the coordinator's current interface at implementation time. The key contract: **delegation re-enters the coordinator, cost tracks to the parent session, depth increments**.

---

### Step 10: Update `_execute_agent` to Pass Delegation Depth

**File**: `modules/backend/agents/coordinator/coordinator.py`

Update `_execute_agent` to accept and forward `delegation_depth`:

```python
async def _execute_agent(
    agent_name: str,
    user_input: str,
    agent_config: AgentConfigSchema,
    delegation_depth: int = 0,
    session_id: str | None = None,
    session_service: Any = None,
    event_bus: Any = None,
) -> dict[str, Any]:
    """Execute any agent dynamically. No agent-specific code needed."""
    registry = get_registry()
    model = _build_model(agent_config.model)
    agent = registry.get_instance(agent_name, model)
    module = _import_agent_module(agent_name)
    deps = _build_agent_deps(
        agent_name,
        agent_config,
        delegation_depth=delegation_depth,
        session_id=session_id,
        session_service=session_service,
        event_bus=event_bus,
    )
    limits = _get_usage_limits()

    result = await module.run_agent(user_input, deps, agent, usage_limits=limits)
    response = _format_response(agent_name, result)

    return {
        "agent_name": response.agent_name,
        "output": response.output,
        **response.metadata,
    }
```

**What changed**: Added `delegation_depth`, `session_id`, `session_service`, `event_bus` parameters and passed them through to `_build_agent_deps`. The defaults preserve backward compatibility with existing callers.

---

### Step 11: Create Delegation Tool Tests

**File**: `tests/unit/backend/agents/tools/test_delegation.py` (NEW)

Create the test directory if needed: `tests/unit/backend/agents/tools/`

```python
"""
Tests for delegation tool implementations.

Tests the pure functions in agents/tools/delegation.py — allowlist
enforcement, depth limiting, coordinator invocation, and agent listing.
No PydanticAI dependency, no LLM calls.
"""

import pytest

from modules.backend.agents.tools.delegation import (
    invoke_agent,
    list_available_agents,
)


# ---- Fixtures ----

@pytest.fixture
def allowed_agents():
    return {"code.qa.agent", "system.health.agent"}


@pytest.fixture
def mock_coordinator():
    """A coordinator callable that returns a mock result."""
    async def _coordinator(agent_name: str, task: str) -> dict:
        return {
            "agent_name": agent_name,
            "output": f"Completed: {task}",
        }
    return _coordinator


@pytest.fixture
def mock_registry_list():
    return [
        {"agent_name": "code.qa.agent", "description": "QA agent", "keywords": ["qa"], "tools": []},
        {"agent_name": "system.health.agent", "description": "Health agent", "keywords": ["health"], "tools": []},
        {"agent_name": "code.coder.agent", "description": "Coder agent", "keywords": ["code"], "tools": []},
    ]


# ---- invoke_agent tests ----

class TestInvokeAgent:
    """Tests for delegation.invoke_agent."""

    @pytest.mark.asyncio
    async def test_successful_delegation(self, allowed_agents, mock_coordinator):
        result = await invoke_agent(
            agent_name="code.qa.agent",
            task="scan for violations",
            coordinator=mock_coordinator,
            allowed_agents=allowed_agents,
            delegation_depth=0,
            max_delegation_depth=2,
        )
        assert result["agent_name"] == "code.qa.agent"
        assert "Completed" in result["output"]

    @pytest.mark.asyncio
    async def test_rejects_unlisted_agent(self, allowed_agents, mock_coordinator):
        with pytest.raises(PermissionError, match="Not authorized"):
            await invoke_agent(
                agent_name="code.coder.agent",
                task="write some code",
                coordinator=mock_coordinator,
                allowed_agents=allowed_agents,
                delegation_depth=0,
                max_delegation_depth=2,
            )

    @pytest.mark.asyncio
    async def test_rejects_at_max_depth(self, allowed_agents, mock_coordinator):
        with pytest.raises(PermissionError, match="Max delegation depth"):
            await invoke_agent(
                agent_name="code.qa.agent",
                task="scan for violations",
                coordinator=mock_coordinator,
                allowed_agents=allowed_agents,
                delegation_depth=2,
                max_delegation_depth=2,
            )

    @pytest.mark.asyncio
    async def test_allows_depth_below_max(self, allowed_agents, mock_coordinator):
        result = await invoke_agent(
            agent_name="code.qa.agent",
            task="scan",
            coordinator=mock_coordinator,
            allowed_agents=allowed_agents,
            delegation_depth=1,
            max_delegation_depth=2,
        )
        assert result["agent_name"] == "code.qa.agent"

    @pytest.mark.asyncio
    async def test_empty_allowlist_rejects_all(self, mock_coordinator):
        with pytest.raises(PermissionError, match="Not authorized"):
            await invoke_agent(
                agent_name="code.qa.agent",
                task="scan",
                coordinator=mock_coordinator,
                allowed_agents=set(),
                delegation_depth=0,
                max_delegation_depth=2,
            )


# ---- list_available_agents tests ----

class TestListAvailableAgents:
    """Tests for delegation.list_available_agents."""

    @pytest.mark.asyncio
    async def test_filters_to_allowlist(self, allowed_agents, mock_registry_list):
        result = await list_available_agents(
            allowed_agents=allowed_agents,
            registry_list=mock_registry_list,
        )
        names = {a["agent_name"] for a in result}
        assert names == {"code.qa.agent", "system.health.agent"}
        assert "code.coder.agent" not in names

    @pytest.mark.asyncio
    async def test_empty_allowlist_returns_empty(self, mock_registry_list):
        result = await list_available_agents(
            allowed_agents=set(),
            registry_list=mock_registry_list,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_missing_agent_in_registry_excluded(self, mock_registry_list):
        result = await list_available_agents(
            allowed_agents={"code.qa.agent", "nonexistent.agent"},
            registry_list=mock_registry_list,
        )
        names = {a["agent_name"] for a in result}
        assert names == {"code.qa.agent"}
```

**Test philosophy**: These test the pure functions directly with mock callables. No PydanticAI, no TestModel, no real agents. The coordinator is a simple async function returning a dict. This validates the access control logic (allowlist, depth limiting) in isolation.

---

### Step 12: Create PM Agent Tests

**File**: `tests/unit/backend/agents/test_pm_agent.py` (NEW)

```python
"""
PM agent tests using PydanticAI TestModel.

Tests the full PM agent chain — LLM -> delegation tool invocation ->
structured PmResult output — without making real API calls. TestModel
generates deterministic, schema-valid responses.
"""

import pytest
from pydantic_ai.models.test import TestModel

from modules.backend.agents.deps.base import FileScope, HorizontalAgentDeps
from modules.backend.agents.schemas import PmResult
from modules.backend.core.config import find_project_root


@pytest.fixture
def mock_coordinator():
    """A coordinator callable that returns a mock result."""
    async def _coordinator(agent_name: str, task: str) -> dict:
        return {
            "agent_name": agent_name,
            "output": f"Completed: {task}",
        }
    return _coordinator


@pytest.fixture
def pm_deps(mock_coordinator):
    """Build HorizontalAgentDeps for PM testing."""
    from modules.backend.agents.coordinator.registry import get_registry

    config = get_registry().get("horizontal.pm.agent")
    return HorizontalAgentDeps(
        project_root=find_project_root(),
        scope=FileScope(read_paths=["docs/", "config/", "logs/"], write_paths=[]),
        config=config,
        allowed_agents=set(config.delegation.allowed_agents),
        max_delegation_depth=config.delegation.max_delegation_depth,
        delegation_depth=0,
        coordinator=mock_coordinator,
    )


@pytest.fixture(autouse=True)
def _reset_agent_instances():
    """Clear registry agent cache before each test so TestModel can be used."""
    from modules.backend.agents.coordinator.registry import get_registry

    get_registry().reset()
    yield
    get_registry().reset()


class TestPmAgentWithTestModel:
    """Tests for horizontal.pm.agent using deterministic TestModel."""

    @pytest.mark.asyncio
    async def test_returns_pm_result_schema(self, pm_deps):
        """TestModel with call_tools=[] validates schema output."""
        from modules.backend.agents.horizontal.pm.agent import create_agent

        agent = create_agent(TestModel(call_tools=[]))
        result = await agent.run("refactor the authentication module", deps=pm_deps)

        assert isinstance(result.output, PmResult)
        assert hasattr(result.output, "summary")
        assert hasattr(result.output, "goal")
        assert hasattr(result.output, "delegations")
        assert hasattr(result.output, "completed")
        assert hasattr(result.output, "blockers")

    @pytest.mark.asyncio
    async def test_usage_is_tracked(self, pm_deps):
        from modules.backend.agents.horizontal.pm.agent import create_agent

        agent = create_agent(TestModel(call_tools=[]))
        result = await agent.run("plan a migration", deps=pm_deps)

        usage = result.usage()
        assert usage.requests >= 1

    @pytest.mark.asyncio
    async def test_run_agent_interface(self, pm_deps):
        """Test the standard run_agent() entry point used by the coordinator."""
        from modules.backend.agents.horizontal.pm.agent import create_agent, run_agent

        agent = create_agent(TestModel(call_tools=[]))
        result = await run_agent("organize the project", pm_deps, agent)

        assert isinstance(result, PmResult)

    @pytest.mark.asyncio
    async def test_agent_has_delegation_tools(self, pm_deps):
        """Verify the agent has invoke_agent and list_available_agents tools registered."""
        from modules.backend.agents.horizontal.pm.agent import create_agent

        agent = create_agent(TestModel(call_tools=[]))
        tool_names = {tool.name for tool in agent._tools.values()}

        assert "invoke_agent" in tool_names
        assert "list_available_agents" in tool_names

    @pytest.mark.asyncio
    async def test_agent_has_filesystem_tools(self, pm_deps):
        """Verify the agent has read_file and list_files tools registered."""
        from modules.backend.agents.horizontal.pm.agent import create_agent

        agent = create_agent(TestModel(call_tools=[]))
        tool_names = {tool.name for tool in agent._tools.values()}

        assert "read_file" in tool_names
        assert "list_files" in tool_names


class TestPmDepsConstruction:
    """Tests for HorizontalAgentDeps construction from config."""

    def test_delegation_config_loaded(self):
        """Verify the PM's delegation config is loaded from YAML."""
        from modules.backend.agents.coordinator.registry import get_registry

        config = get_registry().get("horizontal.pm.agent")
        assert config.delegation is not None
        assert "code.qa.agent" in config.delegation.allowed_agents
        assert config.delegation.max_delegation_depth == 2

    def test_agent_type_is_horizontal(self):
        from modules.backend.agents.coordinator.registry import get_registry

        config = get_registry().get("horizontal.pm.agent")
        assert config.agent_type == "horizontal"

    def test_model_is_sonnet(self):
        from modules.backend.agents.coordinator.registry import get_registry

        config = get_registry().get("horizontal.pm.agent")
        assert "sonnet" in config.model
```

**Test philosophy**: Uses `TestModel(call_tools=[])` to validate structured output without executing tools. Separate delegation tool tests (Step 11) cover the delegation logic. These tests verify: schema compliance, tool registration, config loading, and the `run_agent()` interface.

---

### Step 13: Verify End-to-End and Run Tests

| # | Task | Command/Notes |
|---|------|---------------|
| 13.1 | Run all existing tests | `python -m pytest tests/ -x -q` — ensure nothing is broken |
| 13.2 | Run delegation tool tests | `python -m pytest tests/unit/backend/agents/tools/test_delegation.py -v` |
| 13.3 | Run PM agent tests | `python -m pytest tests/unit/backend/agents/test_pm_agent.py -v` |
| 13.4 | Run full test suite | `python -m pytest tests/ -q` — all green |
| 13.5 | Verify registry discovers PM | `python -c "from modules.backend.agents.coordinator.registry import get_registry; r = get_registry(); print(r.get('horizontal.pm.agent').agent_name)"` |
| 13.6 | Verify module path resolution | `python -c "from modules.backend.agents.coordinator.registry import get_registry; r = get_registry(); print(r.resolve_module_path('horizontal.pm.agent'))"` — should print `modules.backend.agents.horizontal.pm.agent` |
| 13.7 | Verify prompt assembly | `python -c "from modules.backend.agents.coordinator.coordinator import assemble_instructions; print(assemble_instructions('horizontal', 'pm')[:200])"` — should include organization + horizontal + pm layers |

---

### Step 14: Commit

| # | Task | Command/Notes |
|---|------|---------------|
| 14.1 | Stage all new files | `git add modules/backend/agents/horizontal/ modules/backend/agents/tools/delegation.py config/agents/horizontal/ config/prompts/categories/horizontal.md config/prompts/agents/horizontal/ tests/unit/backend/agents/tools/test_delegation.py tests/unit/backend/agents/test_pm_agent.py` |
| 14.2 | Stage modified files | `git add modules/backend/agents/config_schema.py modules/backend/agents/deps/base.py modules/backend/agents/schemas.py modules/backend/agents/coordinator/coordinator.py` |
| 14.3 | Commit | `git commit -m "Add horizontal PM agent with delegation tools"` |

---

## Files Created/Modified Summary

| File | Action | Lines (est.) |
|------|--------|-------------|
| `modules/backend/agents/config_schema.py` | Modified | +10 |
| `modules/backend/agents/deps/base.py` | Modified | +2 |
| `modules/backend/agents/schemas.py` | Modified | +20 |
| `modules/backend/agents/tools/delegation.py` | **Created** | ~100 |
| `modules/backend/agents/horizontal/__init__.py` | **Created** | 0 |
| `modules/backend/agents/horizontal/pm/__init__.py` | **Created** | 0 |
| `modules/backend/agents/horizontal/pm/agent.py` | **Created** | ~130 |
| `modules/backend/agents/coordinator/coordinator.py` | Modified | +30 |
| `config/agents/horizontal/pm/agent.yaml` | **Created** | ~50 |
| `config/prompts/categories/horizontal.md` | **Created** | ~15 |
| `config/prompts/agents/horizontal/pm/system.md` | **Created** | ~35 |
| `tests/unit/backend/agents/tools/__init__.py` | **Created** | 0 |
| `tests/unit/backend/agents/tools/test_delegation.py` | **Created** | ~130 |
| `tests/unit/backend/agents/test_pm_agent.py` | **Created** | ~110 |

**Total**: ~632 lines across 14 files (6 new, 4 modified, 4 init files)

---

## Anti-Patterns — Do NOT

| Anti-pattern | Why prohibited |
|-------------|---------------|
| PM agent importing coordinator directly | Creates circular dependency. The delegation callable is injected via deps. |
| Delegation tool with PydanticAI dependency | Shared tools are pure functions. `RunContext` appears only in the thin wrapper in `agent.py`. |
| PM agent writing files directly | PM has `write: []`. All code modifications go through vertical agents via delegation. |
| Delegation bypassing the coordinator | All delegation goes through the coordinator callable. This ensures middleware (cost tracking, guardrails, budget enforcement) applies to delegated work. |
| Hardcoding allowed_agents in the tool | Allowlist comes from YAML config via `HorizontalAgentDeps`. Tool receives it as a parameter. |
| Depth tracking via global state | Depth is tracked in `HorizontalAgentDeps.delegation_depth`. Each delegated invocation gets `depth + 1` in its deps. |
| PM system prompt in `agent.py` | System prompts live in `config/prompts/`. The `assemble_instructions()` function composes layers 0-2. |
| Testing with real API calls | All agent tests use `TestModel`. `ALLOW_MODEL_REQUESTS = False` in conftest.py prevents real calls. |

---
