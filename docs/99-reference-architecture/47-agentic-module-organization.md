# 47 — Agent Module Organization (Layout, Naming, Access Control)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-02-26*

## Changelog

- 1.0.0 (2026-02-26): Initial agent module organization standard — directory layout, naming conventions, agent types (vertical/horizontal), shared tool architecture, layered prompt system, access control model (tool access, filesystem scope, delegation authority, execution mode), configuration schemas, dependency injection pattern, scaling rationale

---

## Module Status: Required for AI-First Profile

This module is **required** when adopting the AI-First Platform (BFA) profile. It defines the physical organization, naming conventions, and access control model that all other AI-First documents (40-46) assume. Read this document before building any agent.

**Dependencies**: 40-agentic-architecture.md (conceptual foundation), 41-agentic-pydanticai.md (PydanticAI patterns), 04-module-structure.md (module boundaries), 08-python-coding-standards.md (Python conventions).

**Relationship to existing docs**: This document does not replace docs 40, 41, 42, 43, 44, or 46. Those documents define *what* to build — orchestration patterns, PydanticAI implementation, external protocols, interface adapters, channels, sessions. This document defines *where things go, what they're called, and who can access what*. It is the organizational companion to the implementation docs.

---

## Purpose

At 2 agents, any reasonable structure works. At 20 agents, inconsistencies become friction. At 200 agents with hundreds of tools, multiple categories, supervisory agents delegating to specialists, per-agent filesystem restrictions, and containerized execution — the organization model is the difference between a system that scales and one that collapses under its own weight.

This document makes five decisions that affect every file created in the agent system:

1. **Where things live** — directory layout for agents, tools, services, prompts, configs
2. **How things are named** — identity scheme for agents, tools, categories
3. **What types of agents exist** — vertical specialists, horizontal supervisors, coordinator
4. **How tools are shared** — implementation vs registration, shared vs agent-specific
5. **How access is controlled** — tool access, filesystem scope, delegation authority, execution mode

These decisions are not revisited per agent. They are structural — set once, followed always.

---

## Glossary

| Term | Definition |
|------|-----------|
| **Vertical agent** | A domain-specialist agent scoped to a single bounded area (e.g., code quality, system health). Executes tasks directly using domain-specific tools. |
| **Horizontal agent** | A cross-domain supervisory agent that reasons across categories, makes strategic decisions, and delegates to vertical agents. Uses capable models. |
| **Mission Control** | Application code (not an agent) that routes requests, composes middleware, enforces budgets, and yields events. The entry point for all agent interactions. |
| **Objective** | Required metadata on a Playbook definition declaring the strategic business outcome. Fields: `statement`, `category`, `owner`, `priority`, `regulatory_reference`. Used for playbook discovery, audit enrichment, and structured log context. Not an execution layer. |
| **Middleware** | Python decorators that wrap agent execution (guardrails, cost tracking, memory, output formatting). Cross-cutting concerns applied to every agent run. |
| **Shared tool** | A tool implementation in `agents/tools/` that multiple agents can register. Pure function with no PydanticAI dependency. |
| **Agent-specific tool** | A tool implementation that only one agent uses, co-located with that agent's code. |
| **Tool implementation** | A pure async function that performs work — reads files, calls services, runs scans. No `RunContext`, no PydanticAI types. |
| **Tool registration** | A thin `@agent.tool` wrapper in an agent's `agent.py` that delegates to a tool implementation, passing scope from deps. |
| **File scope** | Per-agent configuration defining which filesystem paths the agent can read and write. Enforced at runtime in tool implementations. |
| **Delegation authority** | Per-agent configuration defining which other agents a horizontal agent can invoke. Enforced at runtime in delegation tools. |
| **Prompt layer** | One level in the hierarchical prompt system: organization → category → agent → task. |

---

## Core Principles

**P1: Three concepts, three homes.** Agents, tools, and services are distinct concepts with distinct locations. Agents live in `agents/vertical/` or `agents/horizontal/`. Shared tool implementations live in `agents/tools/`. Business logic lives in `services/`. No concept lives in another concept's home.

**P2: Implementation is separate from registration.** Tool implementations are pure functions with no PydanticAI dependency. Tool registrations are thin `@agent.tool` wrappers that pass scope from deps to the implementation. This separation enables: testing tools without an agent runtime, sharing implementations across agents, and enforcing different scopes per agent on the same underlying operation.

**P3: Scope is configuration, not code.** Which tools an agent can use, which directories it can access, which agents it can delegate to — all defined in YAML, all injected via deps, all enforced at runtime. Adding an agent to a new project with different permissions requires changing a YAML file, not editing Python.

**P4: Names are identity, not hierarchy.** An agent's name (`code.qa.agent`) identifies what it is and what it acts on. It does not encode its permissions, its scope, or its deployment target. Those are configuration concerns in the agent's YAML.

**P5: Prompts are organizational DNA.** The prompt system carries intent from the organization level down to the individual agent. Changing the organization's security posture changes every agent's behavior. Prompts are layered, composable, and managed as configuration — not hardcoded in agent files.

---

## Naming Conventions

### Agents

Every agent has a globally unique identifier in the format `{category}.{name}.agent`:

```
system.health.agent
system.coder.agent
system.prompt_engineer.agent
code.qa.agent
code.review.agent
code.architect.agent
code.coder.agent
data.analysis.agent
security.audit.agent
domain.billing.agent
horizontal.pm.agent
horizontal.architect.agent
horizontal.director.agent
horizontal.reviewer.agent
```

The **category** identifies what the agent acts on. The **name** identifies the specific capability. The **`.agent`** suffix identifies the entity type. Both category and name use `snake_case`.

### Categories

Categories are a controlled vocabulary. Each answers "what does this agent act on?"

| Category | Operates On | Agent Type | Examples |
|----------|------------|-----------|---------|
| `system` | The running platform and its infrastructure | Vertical | `system.health.agent`, `system.coder.agent`, `system.monitor.agent`, `system.prompt_engineer.agent` |
| `code` | Source code and the development process | Vertical | `code.qa.agent`, `code.review.agent`, `code.architect.agent`, `code.coder.agent` |
| `security` | Security boundaries and compliance | Vertical | `security.audit.agent`, `security.vulnerability.agent` |
| `data` | Data, datasets, and data pipelines | Vertical | `data.analysis.agent`, `data.etl.agent`, `data.quality.agent` |
| `domain` | Business-specific logic (varies per deployment) | Vertical | `domain.billing.agent`, `domain.reporting.agent` |
| `comms` | Human communication and notifications | Vertical | `comms.notify.agent`, `comms.digest.agent` |
| `horizontal` | Cross-domain supervision and strategic decisions | Horizontal | `horizontal.pm.agent`, `horizontal.architect.agent`, `horizontal.director.agent` |

All categories except `domain` are universal across deployments. `domain` is the only category whose agents change per project. New categories may be added when an agent does not fit any existing category — categories must not overlap.

The `horizontal` category is reserved for supervisory agents (see "Agent Types" below). All other categories contain vertical agents.

### Do Not Encode Scope in the Name

A `code.coder.agent` deployed for Project X has the same identity as one deployed for Project Y. The scope (which directories, which tools, which budget) is in the YAML config, not the name. This prevents name explosion (`code.coder.project_alpha.agent`, `code.coder.project_beta.agent`) and keeps the naming scheme flat and predictable.

### Tools

Shared tool implementations use dotted names matching their file and function: `{domain}.{action}`.

```
filesystem.read_file
filesystem.write_file
filesystem.list_files
filesystem.search_files
code.run_tests
code.apply_fix
code.lint
system.check_health
system.read_logs
system.service_status
compliance.scan_imports
compliance.scan_datetime
compliance.scan_hardcoded
compliance.scan_file_sizes
compliance.scan_cli_options
delegation.invoke_agent
delegation.list_agents
plan.create_plan
plan.revise_plan
plan.get_status
approval.request_approval
approval.decide
prompt.read_prompt
prompt.write_prompt
```

The first segment matches the filename in `agents/tools/`. `filesystem.read_file` lives in `agents/tools/filesystem.py`, function `read_file`. This makes discovery mechanical: given a tool name, you know exactly which file and function to find.

Agent-specific tools (tools used by only one agent) do not require the dotted naming convention — they are not in the shared namespace.

### Services

Services follow the existing convention from `03-backend-architecture.md`. They are not agent-specific: `ComplianceScannerService`, `NoteService`, `HealthService`. Services live in `modules/backend/services/`.

### Config Files

Agent configurations follow the naming from `41-agentic-pydanticai.md`: `config/agents/{category}/{name}/agent.yaml`. The `agent_name` field inside carries the full dotted identifier including the `.agent` suffix.

---

## Agent Types

The system distinguishes three types of agent-related components. They are structurally similar (PydanticAI `Agent` instances with tools) but serve fundamentally different roles.

### Vertical Agents — Domain Specialists

Vertical agents are bounded to a single domain. They execute tasks directly using domain-specific tools. They do not delegate to other agents. They do not make strategic decisions across domains.

| Dimension | Vertical Agent |
|-----------|---------------|
| **Scope** | One domain (code, system, data, security) |
| **Action** | Executes tasks directly via tools |
| **Model** | Appropriate for domain complexity (Haiku for scanning, Sonnet for coding) |
| **Tools** | Domain-specific (scan files, edit code, check health, query data) |
| **Filesystem** | Scoped to relevant directories per YAML config |
| **Delegation** | None — vertical agents execute, they do not delegate |
| **Budget** | Typically $0.10–$2.00 per invocation |

**Location**: `modules/backend/agents/vertical/{category}/{name}/agent.py`

**Examples**: `system.health.agent`, `code.qa.agent`, `data.analysis.agent`, `security.audit.agent`

### Horizontal Agents — Cross-Domain Supervisors

Horizontal agents cross domain boundaries. They reason about goals, decompose work into tasks, delegate to vertical agents, monitor progress, and make strategic decisions. They are the Thinker tier from `40-agentic-architecture.md` — capable models that decide *what* to do, delegating the *how* to specialists.

| Dimension | Horizontal Agent |
|-----------|-----------------|
| **Scope** | Crosses all domains |
| **Action** | Decomposes goals, delegates to vertical agents, makes decisions |
| **Model** | Capable reasoning models (Sonnet, Opus) — judgment requires quality |
| **Tools** | Delegation tools (invoke agents, create plans), read-only domain access |
| **Filesystem** | Typically read-only on docs/config/logs — does not write code directly |
| **Delegation** | Can invoke vertical agents per allowlist in YAML config |
| **Budget** | Typically $1.00–$10.00 per invocation (includes delegated costs) |

**Location**: `modules/backend/agents/horizontal/{name}/agent.py`

**Examples**:

| Agent | Role | Key Capability |
|-------|------|---------------|
| `horizontal.pm.agent` | Project manager | Decomposes goals into tasks, sequences work, monitors progress, reallocates on failure |
| `horizontal.architect.agent` | Architecture reviewer | Reviews design proposals against principles, approves or rejects structural changes |
| `horizontal.director.agent` | Strategic director | Prioritizes competing requests, allocates budget, sets objectives |
| `horizontal.reviewer.agent` | Quality gate | Reviews agent outputs before delivery — does not delegate, only evaluates |

Horizontal agents delegate through the coordinator, not directly. This ensures middleware (cost tracking, guardrails, observability) applies to delegated work:

```python
# agents/tools/delegation.py — shared tool implementation
async def invoke_agent(
    agent_name: str,
    task: str,
    coordinator,
    allowed_agents: set[str],
) -> dict:
    """Invoke a vertical agent through the coordinator."""
    if agent_name not in allowed_agents:
        raise PermissionError(f"Not authorized to delegate to: {agent_name}")
    return await coordinator.execute(agent_name, task)
```

### Coordinator — Infrastructure, Not Intelligence

The coordinator is application code — a Python module, not a PydanticAI Agent — that routes requests, composes middleware, enforces budgets, and yields events. It does not have a personality, system prompt, or conversational presence. The human never "talks to the coordinator" — it is invisible infrastructure.

**Location**: `modules/backend/agents/coordinator/`

The coordinator:
- Receives all inbound requests from any entry point (API, CLI, Telegram, TUI, WebSocket)
- Routes to the appropriate agent via hybrid routing (rules first, LLM fallback)
- Composes horizontal middleware around every agent execution
- Enforces `UsageLimits` (budget, step count, token limit)
- Publishes events to the event bus (doc 46)
- Handles failures, retries, and escalation
- Returns results to the caller

### Middleware — Cross-Cutting Decorators

Middleware components are Python decorators that wrap agent execution. They are not agents — they do not reason or call LLMs. They intercept the execution lifecycle: before the run, after the run, or both.

**Location**: `modules/backend/agents/coordinator/middleware.py`

The composition order for every agent execution:

```
guardrails → memory → cost_tracking → output_format → agent.run()
```

Every agent passes through the full chain — no exceptions.

### Comparison

| Component | Is an Agent? | Calls LLMs? | Location | Purpose |
|-----------|-------------|------------|----------|---------|
| Vertical agent | Yes | Yes | `agents/vertical/` | Execute domain tasks |
| Horizontal agent | Yes | Yes | `agents/horizontal/` | Supervise, decide, delegate |
| Coordinator | No | No | `agents/coordinator/` | Route, enforce, compose middleware |
| Middleware | No | No | `agents/coordinator/middleware.py` | Cross-cutting concerns (cost, safety, memory) |

---

## Directory Layout

### Complete Annotated Structure

```
modules/backend/
├── agents/
│   ├── __init__.py
│   │
│   ├── coordinator/                        # ROUTING & INFRASTRUCTURE
│   │   ├── __init__.py
│   │   ├── coordinator.py                  # Entry point: handle(), execute()
│   │   ├── registry.py                     # AgentRegistry — discovers all agents from YAML
│   │   ├── router.py                       # Rule-based + LLM routing
│   │   ├── middleware.py                   # Horizontal decorators (guardrails, cost, memory)
│   │   └── models.py                       # CoordinatorRequest, CoordinatorResponse
│   │
│   ├── vertical/                           # DOMAIN SPECIALISTS
│   │   ├── __init__.py
│   │   ├── system/                         # system.* agents
│   │   │   ├── __init__.py
│   │   │   ├── health/
│   │   │   │   ├── __init__.py
│   │   │   │   └── agent.py               # system.health.agent
│   │   │   ├── coder/
│   │   │   │   ├── __init__.py
│   │   │   │   └── agent.py               # system.coder.agent
│   │   │   ├── monitor/
│   │   │   │   ├── __init__.py
│   │   │   │   └── agent.py               # system.monitor.agent
│   │   │   └── prompt_engineer/
│   │   │       ├── __init__.py
│   │   │       └── agent.py               # system.prompt_engineer.agent
│   │   ├── code/                           # code.* agents
│   │   │   ├── __init__.py
│   │   │   ├── qa/
│   │   │   │   ├── __init__.py
│   │   │   │   └── agent.py               # code.qa.agent
│   │   │   ├── review/
│   │   │   │   ├── __init__.py
│   │   │   │   └── agent.py               # code.review.agent
│   │   │   ├── architect/
│   │   │   │   ├── __init__.py
│   │   │   │   └── agent.py               # code.architect.agent
│   │   │   └── coder/
│   │   │       ├── __init__.py
│   │   │       └── agent.py               # code.coder.agent
│   │   ├── data/                           # data.* agents
│   │   │   └── __init__.py
│   │   ├── security/                       # security.* agents
│   │   │   └── __init__.py
│   │   └── domain/                         # domain.* agents (project-specific)
│   │       └── __init__.py
│   │
│   ├── horizontal/                         # CROSS-DOMAIN SUPERVISORS
│   │   ├── __init__.py
│   │   ├── pm/
│   │   │   ├── __init__.py
│   │   │   └── agent.py                   # horizontal.pm.agent
│   │   ├── architect/
│   │   │   ├── __init__.py
│   │   │   └── agent.py                   # horizontal.architect.agent
│   │   ├── director/
│   │   │   ├── __init__.py
│   │   │   └── agent.py                   # horizontal.director.agent
│   │   └── reviewer/
│   │       ├── __init__.py
│   │       └── agent.py                   # horizontal.reviewer.agent
│   │
│   ├── tools/                              # SHARED TOOL IMPLEMENTATIONS
│   │   ├── __init__.py
│   │   ├── filesystem.py                   # read_file, write_file, list_files, search_files
│   │   ├── code.py                         # run_tests, apply_fix, lint
│   │   ├── system.py                       # check_health, read_logs, service_status
│   │   ├── compliance.py                   # scan_imports, scan_datetime, scan_hardcoded, etc.
│   │   ├── delegation.py                   # invoke_agent, list_agents (horizontal agents)
│   │   ├── plan.py                         # create_plan, revise_plan, get_status
│   │   ├── approval.py                     # request_approval, decide
│   │   └── prompt.py                       # read_prompt, write_prompt (prompt engineer)
│   │
│   ├── deps/                               # SHARED DEPENDENCY INJECTION
│   │   ├── __init__.py
│   │   └── base.py                         # BaseAgentDeps, FileScope, ScopeEnforcer
│   │
│   └── schemas.py                          # Shared agent output schemas (Violation, etc.)
│
├── services/                               # BUSINESS LOGIC (unchanged)
│   ├── compliance.py                       # ComplianceScannerService
│   ├── note.py                             # NoteService
│   └── ...
│
config/
├── agents/
│   ├── coordinator.yaml                    # Coordinator config: routing, limits, guardrails
│   ├── system/
│   │   ├── health/agent.yaml               # agent_name: system.health.agent
│   │   ├── coder/agent.yaml                # agent_name: system.coder.agent
│   │   ├── monitor/agent.yaml
│   │   └── prompt_engineer/agent.yaml
│   ├── code/
│   │   ├── qa/agent.yaml                   # agent_name: code.qa.agent
│   │   ├── review/agent.yaml
│   │   ├── architect/agent.yaml
│   │   └── coder/agent.yaml
│   ├── data/
│   ├── security/
│   ├── domain/
│   └── horizontal/
│       ├── pm/agent.yaml                   # agent_name: horizontal.pm.agent
│       ├── architect/agent.yaml
│       ├── director/agent.yaml
│       └── reviewer/agent.yaml
│
└── prompts/
    ├── organization/                       # Layer 0: applies to ALL agents
    │   ├── principles.md                   # Mission, values, priorities
    │   ├── coding_standards.md             # Universal coding principles
    │   ├── security_posture.md             # Security-first mandates
    │   └── communication_style.md          # How agents communicate with humans
    ├── categories/                         # Layer 1: applies to all agents in a category
    │   ├── system.md                       # "Prioritize stability. Log before acting."
    │   ├── code.md                         # "Follow doc 08. Never hardcode values."
    │   ├── data.md                         # "Handle PII per doc 07. Anonymize by default."
    │   ├── security.md                     # "Assume hostile input. Validate everything."
    │   ├── domain.md                       # "Understand the business context."
    │   ├── comms.md                        # "Be clear and concise."
    │   └── horizontal.md                   # "You supervise. You decide. You do not execute."
    └── agents/                             # Layer 2: applies to one specific agent
        ├── system/
        │   ├── health/system.md
        │   ├── coder/system.md
        │   └── prompt_engineer/system.md
        ├── code/
        │   ├── qa/system.md
        │   ├── review/system.md
        │   ├── architect/system.md
        │   └── coder/system.md
        └── horizontal/
            ├── pm/system.md
            ├── architect/system.md
            ├── director/system.md
            └── reviewer/system.md
```

### File Naming Conventions

| Artifact | Path Pattern | Example |
|----------|-------------|---------|
| Vertical agent | `agents/vertical/{category}/{name}/agent.py` | `agents/vertical/code/qa/agent.py` |
| Horizontal agent | `agents/horizontal/{name}/agent.py` | `agents/horizontal/pm/agent.py` |
| Shared tool | `agents/tools/{domain}.py` | `agents/tools/filesystem.py` |
| Deps dataclass | `agents/deps/base.py` | `agents/deps/base.py` |
| Agent YAML config | `config/agents/{category}/{name}/agent.yaml` | `config/agents/code/qa/agent.yaml` |
| Organization prompt | `config/prompts/organization/{name}.md` | `config/prompts/organization/principles.md` |
| Category prompt | `config/prompts/categories/{category}.md` | `config/prompts/categories/code.md` |
| Agent prompt | `config/prompts/agents/{category}/{name}/system.md` | `config/prompts/agents/code/qa/system.md` |
| Agent unit test | `tests/unit/backend/agents/test_{category}_{name}.py` | `tests/unit/backend/agents/test_code_qa.py` |
| Tool unit test | `tests/unit/backend/agents/tools/test_{domain}.py` | `tests/unit/backend/agents/tools/test_filesystem.py` |

### Registry Discovery

The coordinator's registry walker scans `config/agents/` recursively for `agent.yaml` files (`**/agent.yaml`). The `agent_name` field inside each YAML file is the canonical identity. The directory structure is for human and AI organization — the registry does not depend on directory paths for identity.

---

## Tool Architecture

### The Problem

A `read_file` tool is needed by 20+ agents. Each agent may have different filesystem permissions. PydanticAI requires tools to be registered per agent via `@agent.tool` with access to `RunContext[DepsType]`. A shared library of pre-registered tools is not possible within PydanticAI's model.

### The Solution: Separate Implementation from Registration

**Tool implementations** are pure async functions in `agents/tools/`. They accept explicit parameters (file path, scope object, project root) and return results. They have no PydanticAI dependency, no `RunContext`, no agent awareness. They are testable as plain functions.

**Tool registrations** are thin `@agent.tool` wrappers in each agent's `agent.py`. They extract scope and dependencies from `ctx.deps` and delegate to the shared implementation. They are 2-4 lines each.

### Shared Tool Implementation Pattern

```python
# modules/backend/agents/tools/filesystem.py
"""Shared filesystem tool implementations. Pure functions, no PydanticAI dependency."""

from pathlib import Path
from modules.backend.agents.deps.base import FileScope


async def read_file(project_root: Path, file_path: str, scope: FileScope) -> str:
    """Read a file within the allowed scope. Returns content with line numbers."""
    scope.check_read(file_path)
    full_path = project_root / file_path
    if not full_path.is_file():
        return f"Error: file not found: {file_path}"
    lines = full_path.read_text(encoding="utf-8").splitlines()
    numbered = [f"{i:4d}| {line}" for i, line in enumerate(lines, 1)]
    return "\n".join(numbered)


async def write_file(
    project_root: Path, file_path: str, content: str, scope: FileScope,
) -> dict:
    """Write content to a file within the allowed scope."""
    scope.check_write(file_path)
    full_path = project_root / file_path
    full_path.write_text(content, encoding="utf-8")
    return {"success": True, "file": file_path}


async def list_files(
    project_root: Path, directory: str, pattern: str, scope: FileScope,
) -> list[str]:
    """List files matching a pattern within scope."""
    scope.check_read(directory)
    target = project_root / directory
    return sorted(
        str(p.relative_to(project_root))
        for p in target.rglob(pattern)
        if scope.is_readable(str(p.relative_to(project_root)))
    )
```

### Tool Registration Pattern (in agent.py)

```python
# modules/backend/agents/vertical/code/qa/agent.py
from pydantic_ai import Agent, RunContext
from modules.backend.agents.tools import filesystem, compliance
from modules.backend.agents.deps.base import BaseAgentDeps

# ... agent definition ...

@agent.tool
async def read_source_file(ctx: RunContext[QaAgentDeps], file_path: str) -> str:
    """Read a source file with line numbers."""
    return await filesystem.read_file(ctx.deps.project_root, file_path, ctx.deps.scope)

@agent.tool
async def scan_imports(ctx: RunContext[QaAgentDeps]) -> list[dict]:
    """Scan for import violations."""
    return await compliance.scan_imports(
        ctx.deps.project_root, ctx.deps.scope, ctx.deps.config,
    )
```

### Why This Pattern Works at Scale

- **One implementation, many registrations.** Change `filesystem.read_file()` once — all 40 agents that use it get the fix.
- **Different scopes, same code.** The QA agent's wrapper passes a scope that allows `modules/` and `config/`. The architect agent's wrapper passes a scope that allows only `docs/`. Same implementation, different permissions.
- **Testable without PydanticAI.** Tool implementations are plain functions. Test them with `pytest` and real/temp files. No `TestModel`, no `RunContext` mocking.
- **Discoverable.** Given tool name `filesystem.read_file`, the file is `agents/tools/filesystem.py`, the function is `read_file`. Mechanical lookup.

### When to Create an Agent-Specific Tool

Create a tool in the agent's own directory only when:
1. The tool is used by exactly one agent and there is no foreseeable reuse
2. The tool's logic is tightly coupled to the agent's specific output schema
3. Moving it to `agents/tools/` would require generalizing it beyond its useful scope

Agent-specific tools do not need the dotted naming convention. They are imported directly in the agent's `agent.py`.

---

## Prompt Architecture: Layered Intent Engineering

### The Problem

Agent instructions (system prompts) are not just per-agent text. They carry organizational intent: security posture, coding standards, communication style. When the organization changes its priorities, every agent should reflect that change without editing 200 agent files.

### The Solution: Four Prompt Layers

The final instructions assembled for any agent invocation are the concatenation of four layers:

| Layer | Scope | Location | Changes When |
|-------|-------|----------|-------------|
| **0: Organization** | All agents | `config/prompts/organization/*.md` | Organization's mission, values, or policies change |
| **1: Category** | All agents in one category | `config/prompts/categories/{category}.md` | Category-wide standards change |
| **2: Agent** | One specific agent | `config/prompts/agents/{category}/{name}/system.md` | Agent's identity, behavior, or instructions change |
| **3: Task** | One specific invocation | Assembled at runtime by coordinator | Per-request context (user role, session state, history) |

### Layer 0: Organization

Files in `config/prompts/organization/` apply to every agent in the system. They define the organization's DNA:

- `principles.md` — mission statement, core values, decision-making priorities
- `coding_standards.md` — universal coding rules (from doc 08)
- `security_posture.md` — security-first mandates, data handling rules
- `communication_style.md` — how agents communicate with humans (tone, format, escalation)

**Example** (`config/prompts/organization/principles.md`):

```markdown
## Organization Principles

You are part of the BFA platform. These principles govern all your decisions:

1. **Reliability over speed.** Never sacrifice system stability for faster delivery.
2. **Security by default.** Deny access when uncertain. Escalate when unsure.
3. **Transparency.** Log every action. Explain your reasoning. Never hide failures.
4. **Human authority.** Humans can override any decision. Respect kill switches.
5. **Cost awareness.** Prefer cheaper models when quality is sufficient. Track every token.
```

### Layer 1: Category

One file per category in `config/prompts/categories/`. Applies to all agents in that category.

**Example** (`config/prompts/categories/code.md`):

```markdown
## Code Category Standards

All code agents follow these standards without exception:

- Use absolute imports only. Never relative imports.
- Use centralized logging via get_logger(). Never import logging directly.
- Use utc_now() for timestamps. Never datetime.now() or datetime.utcnow().
- Configuration comes from YAML config files. No hardcoded values.
- Files must not exceed 1000 lines. Target 400-500 lines.
- When modifying code, run tests afterward to verify nothing broke.
```

**Example** (`config/prompts/categories/horizontal.md`):

```markdown
## Horizontal Agent Standards

You are a supervisory agent. You do not execute tasks directly.

- Decompose complex requests into discrete tasks for vertical specialists.
- Delegate to the most appropriate vertical agent for each task.
- Monitor progress and reallocate on failure.
- Make decisions when vertical agents need guidance or when tasks conflict.
- You have read-only access to code and documentation. You never write code.
- When uncertain about a decision, escalate to a human rather than guessing.
```

### Layer 2: Agent

One file per agent in `config/prompts/agents/{category}/{name}/system.md`. The agent's specific identity and behavioral instructions.

**Example** (`config/prompts/agents/code/qa/system.md`):

```markdown
## QA Compliance Agent

You audit the codebase for compliance violations and fix auto-fixable issues.

### Workflow
1. Use list_files to discover Python files in scope
2. Run all scan_* tools to detect violations
3. For auto-fixable violations: use apply_fix immediately
4. For violations needing a design decision: set needs_human_decision=True
5. After applying fixes, run tests to verify nothing broke
6. Return a QaAuditResult with all violations and their fix status

### Rules
- Fix auto_fixable violations directly — do not ask the human
- When a fix requires choosing where config goes or how to restructure, escalate
- After fixing, always run tests
- Be precise about file paths and line numbers
```

### Layer 3: Task (Runtime)

Not a file — assembled by the coordinator at invocation time from session state, user context, and conversation history. Uses PydanticAI's `@agent.instructions` decorator:

```python
@agent.instructions
async def add_runtime_context(ctx: RunContext[AgentDeps]) -> str:
    """Inject runtime context into the system prompt."""
    parts = []
    if ctx.deps.session:
        parts.append(f"Session goal: {ctx.deps.session.goal}")
        parts.append(f"Budget remaining: ${ctx.deps.session.cost_budget_remaining:.2f}")
    return "\n".join(parts)
```

### Prompt Assembly

The coordinator assembles the final instructions by concatenating Layers 0-2 at agent initialization time:

```python
def assemble_instructions(category: str, name: str) -> str:
    """Compose layered prompt: organization → category → agent."""
    project_root = find_project_root()
    prompts_dir = project_root / "config" / "prompts"
    layers = []

    org_dir = prompts_dir / "organization"
    if org_dir.exists():
        for org_file in sorted(org_dir.glob("*.md")):
            layers.append(org_file.read_text(encoding="utf-8"))

    cat_file = prompts_dir / "categories" / f"{category}.md"
    if cat_file.exists():
        layers.append(cat_file.read_text(encoding="utf-8"))

    agent_file = prompts_dir / "agents" / category / name / "system.md"
    if agent_file.exists():
        layers.append(agent_file.read_text(encoding="utf-8"))

    return "\n\n".join(layers)
```

Layer 3 (runtime context) is injected separately via PydanticAI's dynamic instructions mechanism, as it changes per invocation.

### The Prompt Engineer Agent

`system.prompt_engineer.agent` is a vertical agent in the `system` category that:
- Has read/write access to `config/prompts/` via the `prompt.read_prompt` and `prompt.write_prompt` shared tools
- Evaluates agent performance by reading execution logs
- Suggests prompt refinements based on observed failures or inefficiencies
- Requires approval gates for changes to Layer 0 (organization) prompts — these affect every agent

---

## Access Control Model

Access control operates on four independent dimensions. Each is configured in the agent's YAML and enforced at runtime. No dimension is encoded in directory structure or agent naming.

### Dimension 1: Tool Access

Which tools an agent can invoke. Declared in the agent's YAML config:

```yaml
tools:
  - filesystem.read_file
  - filesystem.list_files
  - compliance.scan_imports
  - compliance.scan_datetime
  - compliance.scan_hardcoded
  - compliance.scan_file_sizes
  - code.apply_fix
  - code.run_tests
```

**Enforcement**: At agent initialization, only tools listed in the YAML are registered via `@agent.tool`. An agent cannot call a tool that is not in its list — the tool does not exist in the agent's schema. This is a compile-time guarantee, not a runtime check.

### Dimension 2: Filesystem Scope

Which paths an agent can read and write. Declared in the agent's YAML config, injected via `BaseAgentDeps`, enforced in tool implementations:

```yaml
scope:
  read:
    - "modules/"
    - "config/"
    - "tests/"
    - "*.py"
  write:
    - "modules/backend/"
    - "config/"
```

**Enforcement**: The `ScopeEnforcer` class validates every file operation before execution. Tool implementations call `scope.check_read()` or `scope.check_write()` as their first action. A scope violation raises `PermissionError`, which the agent receives as a tool error.

```python
# modules/backend/agents/deps/base.py

@dataclass
class FileScope:
    """Defines which filesystem paths an agent can access."""
    read_paths: list[str]
    write_paths: list[str]

    def check_read(self, rel_path: str) -> None:
        """Raise PermissionError if the path is not in the read scope."""
        if not self._matches(rel_path, self.read_paths):
            raise PermissionError(f"Agent read access denied: {rel_path}")

    def check_write(self, rel_path: str) -> None:
        """Raise PermissionError if the path is not in the write scope."""
        if not self._matches(rel_path, self.write_paths):
            raise PermissionError(f"Agent write access denied: {rel_path}")

    def is_readable(self, rel_path: str) -> bool:
        """Check if a path is within read scope without raising."""
        return self._matches(rel_path, self.read_paths)

    def _matches(self, rel_path: str, allowed: list[str]) -> bool:
        """Check if a path matches any allowed pattern."""
        for pattern in allowed:
            if pattern == "*":
                return True
            if rel_path.startswith(pattern):
                return True
            if pattern.startswith("*") and rel_path.endswith(pattern[1:]):
                return True
        return False
```

### Dimension 3: Delegation Authority

Which other agents a horizontal agent can invoke. Declared in the agent's YAML config. Vertical agents do not have delegation authority.

```yaml
delegation:
  allowed_agents:
    - code.qa.agent
    - code.review.agent
    - code.coder.agent
    - system.health.agent
  max_delegation_depth: 2
```

**Enforcement**: The `delegation.invoke_agent` tool implementation checks the request against the agent's `allowed_agents` set. A delegation to an unlisted agent raises `PermissionError`. `max_delegation_depth` prevents unbounded recursive delegation.

### Dimension 4: Execution Mode (Future)

Where the agent physically runs. Structured in YAML now, implemented in a future phase:

```yaml
execution:
  mode: local
```

| Mode | Behavior | Isolation | When to Use |
|------|----------|-----------|-------------|
| `local` | Runs in the main application process | Filesystem scope provides logical isolation | Default. Platform agents, system agents, read-only agents |
| `container` | Runs in an isolated container with its own filesystem | Container boundary provides physical isolation | Project-scoped coders that must not access system files |

When `mode: container` is implemented, the agent's filesystem scope becomes the container's mount point. The scope configuration (`read`, `write`) applies within the container. The container itself prevents access to anything outside the mount.

### Access Control Matrix (Examples)

| Agent | Tools | Filesystem Read | Filesystem Write | Delegation | Execution |
|-------|-------|----------------|-----------------|-----------|-----------|
| `code.qa.agent` | compliance.*, filesystem.read_file, code.apply_fix, code.run_tests | modules/, config/, tests/, *.py | modules/backend/, config/ | None | local |
| `code.architect.agent` | filesystem.read_file, filesystem.list_files, filesystem.search_files | docs/ | (none) | None | local |
| `system.health.agent` | system.check_health, system.read_logs, filesystem.read_file | logs/, config/ | (none) | None | local |
| `system.coder.agent` | filesystem.*, code.* | modules/, config/, tests/, *.py | modules/, config/, tests/ | None | local |
| `horizontal.pm.agent` | delegation.*, plan.*, filesystem.read_file | docs/, config/, logs/ | (none) | code.*, system.health | local |
| `horizontal.director.agent` | delegation.*, filesystem.read_file | docs/, config/ | (none) | horizontal.pm, code.*, system.* | local |
| `code.coder.agent` (containerized) | filesystem.*, code.* | * (within container) | * (within container) | None | container |

---

## Configuration Schemas

### Vertical Agent YAML

```yaml
# config/agents/{category}/{name}/agent.yaml
# =============================================================================
# Available options:
#   agent_name        - Unique identifier (string, format: {category}.{name}.agent)
#   agent_type        - Agent type (string: vertical | horizontal)
#   description       - Human-readable description for routing (string)
#   enabled           - Enable/disable without code deployment (boolean)
#   model             - LLM model identifier (string, provider:model format)
#   max_budget_usd    - Maximum cost per invocation in USD (decimal)
#   max_input_length  - Maximum input character count (integer)
#   keywords          - Keywords for rule-based routing (list of strings)
#   tools             - Shared tool names this agent can use (list of dotted strings)
#   scope             - Filesystem access control (object)
#     read            - Paths the agent can read (list of strings)
#     write           - Paths the agent can write (list of strings)
#   execution         - Execution mode (object)
#     mode            - Execution environment (string: local | container)
#   rules             - Agent-specific rule configuration (list of objects, optional)
#   exclusions        - Paths/patterns excluded from scanning (object, optional)
# =============================================================================

agent_name: code.qa.agent
agent_type: vertical
description: "Audits the codebase for compliance violations and fixes them"
enabled: true
model: anthropic:claude-haiku-4-5-20251001
max_budget_usd: 0.50
max_input_length: 2000

keywords:
  - compliance
  - qa
  - audit
  - violations
  - check code
  - code review

tools:
  - filesystem.read_file
  - filesystem.list_files
  - compliance.scan_imports
  - compliance.scan_datetime
  - compliance.scan_hardcoded
  - compliance.scan_file_sizes
  - compliance.scan_cli_options
  - compliance.scan_config_files
  - code.apply_fix
  - code.run_tests

scope:
  read:
    - "modules/"
    - "config/"
    - "tests/"
    - "cli.py"
    - "chat.py"
    - "tui.py"
  write:
    - "modules/"
    - "config/"

execution:
  mode: local

rules:
  - id: no_hardcoded_values
    description: "Module-level numeric/string constants that should be in YAML config"
    severity: error
    enabled: true
  # ... additional rules ...

exclusions:
  paths:
    - "scripts/"
    - "docs/"
    - ".venv/"
    - "__pycache__/"
```

### Horizontal Agent YAML

```yaml
# config/agents/horizontal/{name}/agent.yaml
# =============================================================================
# Additional horizontal-specific options:
#   delegation        - Delegation configuration (object)
#     allowed_agents  - Agents this horizontal agent can invoke (list of strings)
#     max_delegation_depth - Maximum recursive delegation depth (integer)
# =============================================================================

agent_name: horizontal.pm.agent
agent_type: horizontal
description: "Decomposes goals into tasks, sequences work, delegates to specialists"
enabled: true
model: anthropic:claude-sonnet-4-20250514
max_budget_usd: 5.00
max_input_length: 32000

keywords:
  - plan
  - project
  - decompose
  - coordinate
  - sequence

tools:
  - delegation.invoke_agent
  - delegation.list_agents
  - plan.create_plan
  - plan.revise_plan
  - plan.get_status
  - filesystem.read_file
  - filesystem.list_files
  - filesystem.search_files

scope:
  read:
    - "docs/"
    - "config/"
    - "logs/"
  write: []

delegation:
  allowed_agents:
    - code.qa.agent
    - code.review.agent
    - code.coder.agent
    - system.health.agent
  max_delegation_depth: 2

execution:
  mode: local
```

### Coordinator YAML

```yaml
# config/agents/coordinator.yaml
# =============================================================================
# Available options:
#   routing           - Routing configuration (object)
#     strategy        - Routing strategy (string: rule | llm | hybrid)
#     llm_model       - Model for LLM-based routing fallback (string)
#     complex_request_agent - Agent for multi-step requests (string)
#     fallback_agent  - Default when no rule matches (string)
#     max_routing_depth - Maximum delegation depth (integer)
#   limits            - Budget and safety limits (object)
#   redis_ttl         - Redis key TTLs in seconds (object)
#   guardrails        - Input validation settings (object)
#   approval          - HITL approval settings (object)
# =============================================================================

routing:
  strategy: hybrid
  llm_model: anthropic:claude-haiku-4-5-20251001
  complex_request_agent: horizontal.pm.agent
  fallback_agent: horizontal.pm.agent
  max_routing_depth: 3

limits:
  max_requests_per_task: 10
  max_tool_calls_per_task: 25
  max_tokens_per_task: 50000
  max_cost_per_plan: 10.00
  max_cost_per_user_daily: 50.00
  task_timeout_seconds: 300
  plan_timeout_seconds: 1800

redis_ttl:
  session: 3600
  approval: 86400
  lock: 30
  result: 3600

guardrails:
  max_input_length: 32000
  injection_patterns:
    - "ignore (all |previous |prior )?instructions"
    - "you are now"
    - "system prompt:"
    - "disregard (your |all )?previous"

approval:
  poll_interval_seconds: 2
  timeout_seconds: 300
```

---

## Dependency Injection Pattern

### BaseAgentDeps

Every agent's deps dataclass extends a common base that carries scope, project root, and config:

```python
# modules/backend/agents/deps/base.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BaseAgentDeps:
    """Common dependencies for all agents."""
    project_root: Path
    scope: FileScope
    config: dict[str, Any]


@dataclass
class QaAgentDeps(BaseAgentDeps):
    """QA agent adds progress callback for streaming."""
    on_progress: Any = None

    def emit(self, event: dict) -> None:
        if self.on_progress is not None:
            self.on_progress(event)


@dataclass
class HorizontalAgentDeps(BaseAgentDeps):
    """Horizontal agents add delegation authority."""
    allowed_agents: set[str] = field(default_factory=set)
    max_delegation_depth: int = 2
    coordinator: Any = None
```

### Deps Construction

The coordinator constructs deps from the agent's YAML config at invocation time:

```python
def build_deps(agent_config: dict, project_root: Path) -> BaseAgentDeps:
    """Construct agent deps from YAML configuration."""
    scope_config = agent_config.get("scope", {})
    scope = FileScope(
        read_paths=scope_config.get("read", []),
        write_paths=scope_config.get("write", []),
    )
    return BaseAgentDeps(
        project_root=project_root,
        scope=scope,
        config=agent_config,
    )
```

---

## The Call Chain

### Vertical Agent Invocation

```
User request ("scan my code for violations")
    │
    ▼
Coordinator
    ├── 1. Route: keyword match → code.qa.agent
    ├── 2. Build deps: load YAML, construct FileScope, inject config
    ├── 3. Assemble instructions: Layer 0 + Layer 1 + Layer 2 + Layer 3
    ├── 4. Compose middleware: guardrails → memory → cost_tracking → agent.run()
    ├── 5. Enforce UsageLimits(request_limit=10, total_tokens_limit=50000)
    │
    ▼
code.qa.agent (PydanticAI Agent)
    ├── LLM reasons, decides to call scan_imports tool
    │
    ▼
@agent.tool scan_imports (thin wrapper in agent.py)
    ├── Extracts scope from ctx.deps
    │
    ▼
compliance.scan_imports (shared implementation in agents/tools/compliance.py)
    ├── scope.check_read() on each file path
    ├── Calls ComplianceScannerService methods
    │
    ▼
ComplianceScannerService (business logic in services/compliance.py)
    ├── Performs scanning, returns findings
    │
    ▼
Result flows back through the chain → Coordinator → Caller
```

### Horizontal Agent Delegation

```
User request ("refactor the authentication module")
    │
    ▼
Coordinator
    ├── 1. Route: complex request → horizontal.pm.agent
    │
    ▼
horizontal.pm.agent (PydanticAI Agent, Sonnet model)
    ├── LLM reasons: "I need to review current code, design new approach, implement, test"
    ├── Calls delegation.invoke_agent("code.review.agent", "review auth module")
    │
    ▼
@agent.tool invoke_agent (thin wrapper)
    ├── Checks: "code.review.agent" in allowed_agents? ✓
    │
    ▼
delegation.invoke_agent (shared implementation in agents/tools/delegation.py)
    ├── Calls coordinator.execute("code.review.agent", task)
    │
    ▼
Coordinator (re-enters for delegated work)
    ├── Full middleware chain applies to delegated agent
    ├── Cost tracked, budget enforced, events published
    │
    ▼
code.review.agent executes → result returned to PM
    │
    ▼
horizontal.pm.agent continues reasoning with the review result
    ├── Calls delegation.invoke_agent("code.coder.agent", "implement new auth")
    ├── ... continues until plan is complete ...
```

---

## Adding a New Vertical Agent (Walkthrough)

Adding `security.audit.agent` from zero to working:

**Step 1: Create the YAML config**

```
config/agents/security/audit/agent.yaml
```

Define `agent_name`, `agent_type`, `model`, `tools`, `scope`, `keywords`.

**Step 2: Create the prompt**

```
config/prompts/agents/security/audit/system.md
```

Write the agent's Layer 2 identity and behavioral instructions.

**Step 3: Create the agent file**

```
modules/backend/agents/vertical/security/audit/agent.py
```

Import shared tool implementations, define output schema, create `Agent` instance, register thin tool wrappers. Target: 60-120 lines.

**Step 4: Create or extend services**

If the agent needs business logic that doesn't exist yet, create it in `modules/backend/services/`. If existing services suffice, skip this step.

**Step 5: Write tests**

- Tool implementation tests: test shared tools (if new ones were added) with real/temp files
- Agent tests: use `TestModel` to verify schema compliance and tool invocation
- Set `ALLOW_MODEL_REQUESTS = False` in `tests/conftest.py`

**Step 6: Verify discovery**

The coordinator's registry walker auto-discovers the new agent from its YAML config. No coordinator changes needed.

---

## Adding a New Shared Tool (Walkthrough)

Adding `security.scan_vulnerabilities` to `agents/tools/security.py`:

**Step 1: Write the implementation**

```python
# agents/tools/security.py
async def scan_vulnerabilities(
    project_root: Path, scope: FileScope, config: dict,
) -> list[dict]:
    """Scan for known vulnerability patterns in dependencies."""
    scope.check_read("requirements.txt")
    # ... implementation ...
```

Pure function. No PydanticAI dependency. Accepts explicit parameters.

**Step 2: Write tests**

```python
# tests/unit/backend/agents/tools/test_security.py
async def test_scan_vulnerabilities(tmp_path):
    scope = FileScope(read_paths=["*"], write_paths=[])
    results = await scan_vulnerabilities(tmp_path, scope, {})
    assert isinstance(results, list)
```

**Step 3: Register in agents that need it**

Add `security.scan_vulnerabilities` to the agent's YAML config `tools` list, then add a thin wrapper in the agent's `agent.py`.

---

## Scaling Scenarios

### 200 agents — finding what you need

```bash
# List all categories
ls config/agents/
# system/  code/  data/  security/  domain/  horizontal/  comms/

# List all code agents
ls config/agents/code/
# qa/  review/  architect/  coder/  docs/  refactor/

# Find which agents use a specific tool
grep -rl "compliance.scan_imports" config/agents/
# config/agents/code/qa/agent.yaml
# config/agents/code/review/agent.yaml
```

### Shared tool changes — propagation

Change `agents/tools/filesystem.py:read_file()`. Every agent that wraps it picks up the change. No duplication to update. One implementation, one test, one fix.

### New team member — where to look

Given agent name `code.qa.agent`:
- **Config**: `config/agents/code/qa/agent.yaml`
- **Code**: `modules/backend/agents/vertical/code/qa/agent.py`
- **Prompts**: `config/prompts/agents/code/qa/system.md`
- **Test**: `tests/unit/backend/agents/test_code_qa.py`

Every path is derivable from the agent name. No guessing.

### Organization-wide policy change

Update `config/prompts/organization/security_posture.md`. Every agent — vertical and horizontal, across all categories — inherits the change at their next invocation. No code changes, no agent file edits, no redeployment.

---

## Anti-Patterns

| Anti-pattern | Why prohibited |
|-------------|---------------|
| Business logic in tool wrappers | Tool wrappers are thin adapters (2-4 lines). Business logic belongs in services. Scanning logic, data transformation, validation — all in `services/`. |
| Tool implementation with `RunContext` | Shared tool implementations must be pure functions with no PydanticAI dependency. `RunContext` appears only in the thin `@agent.tool` wrapper in `agent.py`. |
| Hardcoded system prompt in agent.py | System prompts live in `config/prompts/`. The coordinator assembles layered instructions at initialization. Hardcoding skips the organization and category layers. |
| Scope enforcement in the agent file | Scope checks happen in shared tool implementations via `FileScope`. Agent files pass scope from deps — they do not implement access control logic. |
| Encoding scope in agent names | `code.coder.project_x.agent` is wrong. The agent is `code.coder.agent` with project-specific scope in its YAML config. |
| Vertical agent delegating to another agent | Vertical agents execute directly. Only horizontal agents delegate. If a vertical agent needs another agent's output, the request should go through a horizontal agent that coordinates both. |
| Agent calling another agent without the coordinator | Bypasses routing, observability, loop prevention, budget enforcement, and middleware composition. All delegation goes through the coordinator. |
| Duplicating tool implementations across agents | If two agents need the same tool, the implementation belongs in `agents/tools/`. Each agent registers a thin wrapper. |
| Organization-level prompts edited without approval | Changes to Layer 0 prompts affect every agent. The `system.prompt_engineer.agent` should have approval gates on organization-level prompt modifications. |
| Module-level agent singletons without lazy initialization | Agent instances should be created lazily (on first use) to avoid import-time configuration errors and to support `TestModel` overrides in tests. |
| Tools that call repositories directly | Tools call services, not repositories. This is the same rule as API endpoint handlers (doc 03) and MCP tool functions (doc 42). |

---

## Relationship to Other Documents

| Document | What It Defines | What This Document Adds |
|----------|----------------|------------------------|
| **40-agentic-architecture.md** | Conceptual architecture: phases, principles, orchestration patterns, AgentTask primitive | Where agents live, how they're named, what types exist |
| **41-agentic-pydanticai.md** | PydanticAI implementation: coordinator, agent-as-tool delegation, middleware, testing, database schema | Complete directory layout, shared tool architecture, layered prompts, access control YAML schemas |
| **42-agent-first-infrastructure.md** | MCP, A2A, agent identity, intent APIs | No overlap — doc 42 is about external agent interop |
| **43-ai-first-interface-design.md** | Adapter registry, service factory, discovery endpoints | Reinforces: tools are thin adapters, services are the universal contract |
| **44-multi-channel-gateway.md** | Channel adapters, sessions, WebSocket, security | No overlap — doc 44 is about channel delivery |
| **46-event-session-architecture.md** | Session model, event bus, streaming coordinator, plans, memory, approvals | No overlap — doc 46 is about runtime session behavior |
| **04-module-structure.md** | Module boundaries and communication | This document follows module structure conventions within the agent module |
| **08-python-coding-standards.md** | Python file organization, imports, logging | All agent code follows doc 08 standards |

### Dependency

This document depends on docs 40, 41, 04, and 08. It does not depend on docs 42, 43, 44, or 46 — those are composable siblings, not prerequisites.

---

## Related Documentation

- [40-agentic-architecture.md](40-agentic-architecture.md) — Conceptual architecture (phases, orchestration patterns, AgentTask primitive)
- [41-agentic-pydanticai.md](41-agentic-pydanticai.md) — PydanticAI implementation (coordinator, middleware, testing, database)
- [42-agent-first-infrastructure.md](42-agent-first-infrastructure.md) — External agent interop (MCP, A2A, agent identity)
- [43-ai-first-interface-design.md](43-ai-first-interface-design.md) — Adapter registry, service factory, discovery endpoints
- [44-multi-channel-gateway.md](44-multi-channel-gateway.md) — Channel delivery, sessions, WebSocket, security
- [46-event-session-architecture.md](46-event-session-architecture.md) — Session model, event bus, streaming, plans, memory, approval gates
- [04-module-structure.md](04-module-structure.md) — Module boundaries and communication
- [08-python-coding-standards.md](08-python-coding-standards.md) — Python conventions (absolute imports, logging, file size limits)
