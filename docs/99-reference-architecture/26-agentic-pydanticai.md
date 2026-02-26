# 26 - Agentic AI: PydanticAI Implementation (Optional Module)

*Version: 2.1.0*
*Author: Architecture Team*
*Created: 2026-02-18*

## Changelog

- 2.1.0 (2026-02-24): Added channel/session_type/tool_access_level to CoordinatorRequest, added WebSocket entry point example with run_stream(), added gateway-mediated channel adapter note referencing 29-multi-channel-gateway.md
- 2.0.0 (2026-02-19): Rewrote with PydanticAI-native patterns — coordinator as PydanticAI Agent, agent-as-tool delegation with cost propagation, UsageLimits for budget enforcement, decorator-based middleware, merged entry points/HITL/database models from research docs, removed LangGraph, fixed all hardcoded values and datetime issues
- 1.1.0 (2026-02-18): Added concept-to-implementation mapping, data model mapping, reconciled SQL schema with AgentTask primitive
- 1.0.0 (2026-02-18): Initial PydanticAI implementation guide

---

## Module Status: Optional

This module is the **implementation companion** to **[25-agentic-architecture.md](25-agentic-architecture.md)**, which defines the conceptual architecture (phases, principles, orchestration patterns, primitive). This document specifies how those concepts are realized using PydanticAI.

**Do not adopt this module without first reading 25-agentic-architecture.md.**

**Dependencies**: 25-agentic-architecture.md, 08-llm-integration.md, 06-event-architecture.md.

---

## Glossary

| Term | Definition |
|------|------------|
| **Vertical agent** | A domain-specialist agent that handles a bounded subject area (e.g., report generation, data analysis). One vertical agent per domain. |
| **Horizontal agent** | A cross-cutting concern that wraps vertical agent execution (e.g., cost tracking, guardrails, memory management). Not domain-aware. |
| **Agent coordinator** | The PydanticAI Agent that receives all inbound requests, selects the appropriate vertical agent via tool delegation, and returns results. |
| **Agent tool** | A function registered with a PydanticAI agent that the LLM may invoke. Tools call services; they do not call repositories or external APIs directly. |
| **Agent context** | The runtime data passed into an agent run: conversation history, session state, dependencies (service instances, credentials). |
| **Checkpoint** | A serialised snapshot of agent execution state written to PostgreSQL, enabling resume after interruption. |
| **Human-in-the-loop (HITL) gate** | A pause point in agent execution that suspends the run, stores a pending approval record, and resumes only after an authorised actor approves via API. |
| **Capability declaration** | A structured metadata object attached to each vertical agent that the coordinator uses to make routing decisions. |

---

## Concept-to-Implementation Mapping

| Concept (Doc 25) | Implementation (This Document) |
|-------------------|-------------------------------|
| **AgentTask primitive** | `agent_runs` table + `agent_messages` table |
| **Orchestrator** | PydanticAI `Agent` with agent-delegation tools (Section 7) |
| **Router Agent** | `Agent` with `output_type=RoutingDecision` (Section 7) |
| **Agent Registry** | `VerticalAgentRegistry` class loading from YAML config |
| **Tool Registry** | Tool definitions in agent YAML + `@agent.tool` decorators |
| **Execution Engine (ReAct loop)** | PydanticAI's built-in `agent.run()` / `agent.run_stream()` |
| **Horizontal middleware** | Python decorators wrapping agent run calls (Section 9) |
| **Agent-as-tool delegation** | PydanticAI tool calling child `agent.run(usage=ctx.usage)` |
| **Budget enforcement** | PydanticAI `UsageLimits` per run |
| **Kill switch** | API endpoint + task status update to `cancelled` |
| **Approval gates** | `agent_pending_approvals` table + Redis polling |
| **Reasoning chain** | `reasoning` JSONB field on `agent_runs` |
| **Memory (Phase 3)** | pgvector extension + Memory decorator |
| **Feedback (Phase 4)** | `feedback` field on `agent_runs` + quality scores |

---

## Technology Decision: PydanticAI

**Package:** `pydantic-ai` (v1.61.0+, stable post-1.0 API, MIT license)

PydanticAI is chosen because:
- Built by the Pydantic/FastAPI team — `RunContext[DepsT]` mirrors FastAPI's `Depends()` pattern
- `output_type` accepts any Pydantic `BaseModel` — same model validates API responses and LLM output
- Deterministic testing via `TestModel`, `FunctionModel`, and `ALLOW_MODEL_REQUESTS = False`
- Agent-as-tool delegation with automatic cost propagation (`usage=ctx.usage`)
- `instructions` parameter is NOT retained in message history across handoffs — prevents prompt leakage
- MIT license, model-agnostic (20+ providers), minimal abstraction tax
- Tools are plain Python functions with type annotations — no custom DSL

For the full framework evaluation, see **[Why PydanticAI is the right agent framework](../../98-research/04-Why%20PydanticAI%20is%20the%20right%20agent%20framework%20for%20your%20FastAPI%20stack.md)**.

---

## Key PydanticAI Patterns

This section defines the framework patterns used throughout the rest of the document.

### Agent Definition

```python
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from dataclasses import dataclass

@dataclass
class MyDeps:
    db: AsyncSession
    user_id: str

class MyOutput(BaseModel):
    summary: str
    confidence: float

agent = Agent(
    'anthropic:claude-sonnet-4-20250514',   # model from config, not hardcoded
    deps_type=MyDeps,
    output_type=MyOutput,
    instructions='You are a specialist agent.',
)
```

The `Agent` is generic as `Agent[DepsT, OutputT]`. The `instructions` parameter is preferred over `system_prompt`.

### Tool Definition

```python
@agent.tool
async def fetch_data(ctx: RunContext[MyDeps], record_id: str) -> dict:
    """Fetch a record by ID. Returns the record fields."""
    return await ctx.deps.db.get(record_id)
```

Tools are plain async functions. `RunContext[DepsT]` provides typed access to dependencies. The framework generates JSON schemas from type annotations and extracts parameter descriptions from docstrings.

### Agent-as-Tool Delegation

The primary multi-agent pattern. A parent agent calls a child agent inside a tool function, with `usage=ctx.usage` propagating cost tracking automatically:

```python
coordinator = Agent('anthropic:claude-sonnet-4-20250514', instructions='Route to specialists.')
billing_agent = Agent('anthropic:claude-haiku-4.5', output_type=BillingResponse)

@coordinator.tool
async def handle_billing(ctx: RunContext[CoordinatorDeps], query: str) -> str:
    """Delegate billing questions to the billing specialist."""
    result = await billing_agent.run(query, deps=ctx.deps.billing_deps, usage=ctx.usage)
    return result.output.model_dump_json()
```

The child agent's cost is included in the parent's usage tracking. No manual cost aggregation needed.

### Budget Enforcement

```python
from pydantic_ai import UsageLimits

result = await agent.run(
    user_message,
    deps=deps,
    usage_limits=UsageLimits(
        request_limit=10,         # max LLM calls per run
        tool_calls_limit=25,      # max tool invocations per run
        total_tokens_limit=50000, # max tokens per run
    ),
)
```

When limits are exceeded, PydanticAI raises `UsageLimitExceeded`. No custom budget checking needed.

### Dynamic System Prompts

```python
@agent.instructions
async def add_context(ctx: RunContext[MyDeps]) -> str:
    """Dynamically add user context to the system prompt."""
    user = await ctx.deps.db.get_user(ctx.deps.user_id)
    return f"Current user: {user.name}, role: {user.role}"
```

### Dynamic Tool Filtering

```python
from pydantic_ai.tools import ToolDefinition

async def filter_by_role(
    ctx: RunContext[MyDeps], tool_defs: list[ToolDefinition]
) -> list[ToolDefinition]:
    """Hide tools the current user is not authorized to use."""
    allowed = TOOL_PERMISSIONS.get(ctx.deps.user_role, set())
    return [td for td in tool_defs if td.name in allowed]

secured_agent = Agent('openai:gpt-4o', deps_type=MyDeps, prepare_tools=filter_by_role)
```

### Run Methods

| Method | Use Case |
|--------|----------|
| `agent.run()` | Standard async execution, returns complete result |
| `agent.run_stream()` | Streaming response (SSE, WebSocket) |
| `agent.iter()` | Node-level iteration for fine-grained control |
| `agent.run_sync()` | Synchronous execution (testing, scripts only) |

### Message History Serialization

PydanticAI message history is model-independent and fully serializable — this is the bridge between the agent runtime and your persistence layer:

```python
from pydantic_ai import Agent, ModelMessagesTypeAdapter

agent = Agent('openai:gpt-4o', instructions='Be helpful.')

result1 = await agent.run('What is the capital of France?')

# Serialize for PostgreSQL storage
json_bytes: bytes = result1.all_messages_json()

# Restore from storage
restored = ModelMessagesTypeAdapter.validate_json(json_bytes)

# Continue conversation with history
result2 = await agent.run('And Germany?', message_history=restored)
```

**History processors** trim context before sending to the LLM, keeping costs under control for long conversations:

```python
async def keep_recent(messages: list) -> list:
    """Keep only the 10 most recent messages to manage context window."""
    return messages[-10:]

trimmed_agent = Agent('openai:gpt-4o', history_processors=[keep_recent])
```

### Output Validators

Validate agent output before it is returned, with automatic retry on failure:

```python
@agent.output_validator
async def validate_output(ctx: RunContext[MyDeps], result: MyOutput) -> MyOutput:
    blocked = ["api_key", "password", "secret"]
    for term in blocked:
        if term.lower() in result.summary.lower():
            raise ModelRetry("Response contains sensitive data. Regenerate without it.")
    return result
```

If validation fails, PydanticAI sends the error back to the LLM and retries (up to `retries` count on the Agent).

---

## Agent Naming Convention

### Agent Identity Format

Every agent has a globally unique identifier in the format `{category}.{name}.agent`:

```
system.health.agent
code.qa.agent
domain.billing.agent
security.vulnerability.agent
```

The **category** identifies what the agent operates on. The **name** identifies the specific capability. The **`.agent`** suffix identifies the entity type. Both category and name use `snake_case`.

The `.agent` suffix distinguishes agents from other entity types that may share the same `{category}.{name}` namespace in logs, databases, and search results:

| Entity Type | Example | Suffix |
|------------|---------|--------|
| Agent | `code.qa.agent` | `.agent` |
| Tool | `code.qa.tool` | `.tool` |
| Skill (A2A) | `code.qa.skill` | `.skill` |

### Categories

Categories are a controlled vocabulary. Each answers "what does this agent act on?"

| Category | Operates On | Examples |
|----------|------------|---------|
| `system` | The running platform and infrastructure | `system.health.agent`, `system.deploy.agent`, `system.monitor.agent` |
| `code` | The source code and development process | `code.qa.agent`, `code.review.agent`, `code.docs.agent` |
| `security` | Security boundaries and compliance | `security.audit.agent`, `security.vulnerability.agent` |
| `data` | Data, datasets, and data pipelines | `data.quality.agent`, `data.etl.agent`, `data.archival.agent` |
| `domain` | Business-specific logic (varies per deployment) | `domain.billing.agent`, `domain.reporting.agent` |
| `comms` | Human communication and notifications | `comms.notify.agent`, `comms.digest.agent`, `comms.translation.agent` |

All categories except `domain` are universal across deployments. `domain` is the only category whose agents change per project.

New categories may be added to this table when an agent does not fit any existing category. Categories must not overlap — if two categories could both claim an agent, the category closest to what the agent **acts on** wins.

### File and Directory Mapping

The directory structure uses `{category}/{name}/` — each agent gets its own directory. All agent Python files are named `agent.py`. All agent config files are named `agent.yaml`. The identity comes from the directory path, not the filename:

| Artifact | Path Pattern | Example |
|----------|-------------|---------|
| Agent config | `config/agents/{category}/{name}/agent.yaml` | `config/agents/system/health/agent.yaml` |
| Agent code | `modules/backend/agents/vertical/{category}/{name}/agent.py` | `modules/backend/agents/vertical/system/health/agent.py` |
| Agent tools | `modules/agents/tools/{category}/{name}/` | `modules/agents/tools/code/qa/` |
| System prompt | `modules/agents/prompts/{category}/{name}/system.md` | `modules/agents/prompts/code/qa/system.md` |
| Agent deps | `modules/agents/deps/{category}/{name}.py` | `modules/agents/deps/code/qa.py` |
| Unit test | `tests/unit/backend/agents/test_{category}_{name}.py` | `test_code_qa.py` |

The `agent_name` field in the YAML config file carries the full identifier including the `.agent` suffix:

```yaml
# config/agents/system/health/agent.yaml
agent_name: system.health.agent
```

The Python import path mirrors the identity naturally:

```python
from modules.backend.agents.vertical.system.health.agent import run_health_agent
from modules.backend.agents.vertical.code.qa.agent import run_qa_agent
```

### Registry Discovery

The coordinator's registry loader walks `config/agents/` recursively for `agent.yaml` files (`**/agent.yaml`). The `agent_name` field inside each YAML file is the canonical identity — the directory structure is for human and AI organization.

### CLI Usage

Direct invocation uses the full dotted name:

```bash
python chat.py --agent system.health.agent --message "check everything"
python chat.py --agent code.qa.agent --message "run compliance audit"
```

Keyword-based routing does not require knowing the agent name — the user says "check system health" and the coordinator routes based on keywords.

The `--list-agents` output groups agents by category:

```
system:
  system.health.agent   — Checks system health and provides diagnostic advice
code:
  code.qa.agent         — Audits codebase for compliance violations and fixes them
```

---

## Agent Taxonomy

### Service/Agent Boundary Rule

Logic belongs in `modules/backend/services/` if it operates on domain data without an LLM in the loop. Logic belongs in `modules/agents/` if an LLM decides what to do or what to call.

| Condition | Location |
|-----------|----------|
| Pure data access, transformation, or mutation | `modules/backend/services/` |
| LLM selects which operation to perform | `modules/agents/vertical/` |
| Cross-cutting execution concern (cost, safety, memory) | `modules/agents/horizontal/` |
| Routing and orchestration | `modules/agents/coordinator/` |

### Vertical Agents (Domain Specialists)

A vertical agent is a PydanticAI `Agent` instance scoped to a single domain. It maps to the "Specialist" tier in 25-agentic-architecture.md. Each vertical agent owns its system prompt, tool set, output schema, and capability declaration.

One file per vertical agent. One vertical agent per domain.

### Horizontal Agents (Middleware Decorators)

A horizontal agent is a Python decorator that wraps a vertical agent's execution. It does not select domains. It does not call LLMs directly. It intercepts the execution lifecycle: before the run, after the run, or both.

The composition order for every agent execution:

```
guardrails → memory → cost_tracking → output_format → agent.run()
```

### Agent Coordinator

The coordinator is a PydanticAI `Agent` that serves as the entry point for all agent requests. It delegates to vertical agents via tool functions (agent-as-tool pattern), with automatic cost propagation via `usage=ctx.usage`. When rule-based routing matches, the coordinator agent is bypassed entirely for cost savings.

---

## Module Structure

Agent names follow the `{category}.{name}` convention defined in "Agent Naming Convention" above. The category maps to a subdirectory in config, code, and tests.

```
modules/
├── agents/
│   ├── __init__.py
│   ├── coordinator/
│   │   ├── __init__.py
│   │   ├── coordinator.py          # Coordinator Agent + handle() function
│   │   ├── registry.py             # VerticalAgentRegistry
│   │   ├── router_rule.py          # Rule-based routing logic
│   │   └── models.py               # CoordinatorRequest, CoordinatorResponse
│   ├── vertical/
│   │   ├── __init__.py
│   │   ├── base.py                 # AgentCapability dataclass
│   │   ├── system/                 # system.* agents
│   │   │   ├── __init__.py
│   │   │   └── health/             # system.health.agent
│   │   │       ├── __init__.py
│   │   │       └── agent.py
│   │   ├── code/                   # code.* agents
│   │   │   ├── __init__.py
│   │   │   └── qa/                 # code.qa.agent
│   │   │       ├── __init__.py
│   │   │       └── agent.py
│   │   └── {category}/             # One subdir per category
│   │       ├── __init__.py
│   │       └── {name}/             # One subdir per agent
│   │           ├── __init__.py
│   │           └── agent.py        # Always named agent.py
│   ├── horizontal/
│   │   ├── __init__.py
│   │   ├── cost_tracking.py        # Cost tracking decorator
│   │   ├── guardrails.py           # Input/output guardrails decorator
│   │   ├── memory.py               # Short/long-term memory decorator
│   │   └── output_format.py        # Output normalization decorator
│   ├── tools/
│   │   ├── __init__.py
│   │   └── {category}.{name}/
│   │       └── {tool_name}.py      # One file per tool group
│   ├── prompts/
│   │   └── {category}.{name}/
│   │       ├── system.md           # System prompt (Markdown)
│   │       └── examples.md         # Few-shot examples
│   ├── deps/
│   │   ├── __init__.py
│   │   └── {category}.{name}.py    # Deps dataclass per agent
│   ├── models.py                   # SQLAlchemy models
│   ├── repository.py               # Data access layer
│   ├── schemas.py                  # Pydantic API schemas
│   └── exceptions.py               # Module-specific exceptions
├── backend/
│   └── ...                         # Unchanged existing structure
config/
└── agents/
    ├── coordinator.yaml
    ├── system/                     # system.* agent configs
    │   └── health/
    │       └── agent.yaml          # agent_name: system.health.agent
    ├── code/                       # code.* agent configs
    │   └── qa/
    │       └── agent.yaml          # agent_name: code.qa.agent
    └── {category}/
        └── {name}/
            └── agent.yaml          # agent_name: {category}.{name}.agent
tests/
└── agents/
    ├── vertical/
    │   └── test_{category}_{name}.py
    ├── horizontal/
    │   └── test_{horizontal_name}.py
    ├── coordinator/
    │   └── test_coordinator.py
    └── integration/
        └── test_{category}_{name}_flow.py
```

### File Naming Conventions

| Artifact | Convention | Example |
|----------|-----------|---------|
| Vertical agent | `vertical/{category}/{name}/agent.py` | `vertical/system/health/agent.py` |
| Horizontal | `{concern}.py` | `cost_tracking.py` |
| Tool file | `{tool_group}.py` under `tools/{category}/{name}/` | `tools/domain/billing/fetch.py` |
| Deps dataclass | `deps/{category}/{name}.py` | `deps/domain/billing.py` |
| System prompt | `prompts/{category}/{name}/system.md` | `prompts/domain/billing/system.md` |
| Config | `config/agents/{category}/{name}/agent.yaml` | `config/agents/domain/billing/agent.yaml` |
| Unit test | `tests/agents/vertical/test_{category}_{name}.py` | `test_code_qa.py` |

---

## Coordinator Pattern

### Hybrid Routing

Deterministic rules handle obvious cases cheaply. The PydanticAI coordinator agent handles ambiguous queries via tool delegation.

```python
from pydantic_ai import Agent, RunContext, UsageLimits
from modules.agents.coordinator.models import CoordinatorRequest, CoordinatorResponse
from modules.agents.coordinator.registry import VerticalAgentRegistry
from modules.agents.coordinator.router_rule import RuleBasedRouter
from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CoordinatorDeps:
    registry: VerticalAgentRegistry
    request: CoordinatorRequest


def _build_coordinator_agent(config: dict, registry: VerticalAgentRegistry) -> Agent:
    """Build the coordinator agent with delegation tools for each registered vertical."""
    caps = "\n".join(f"- {c.agent_name}: {c.description}" for c in registry.all_capabilities())
    prompt = f"Route user requests to the appropriate specialist agent.\nAvailable agents:\n{caps}"

    coordinator = Agent(
        config["routing"]["llm_model"],
        deps_type=CoordinatorDeps,
        output_type=CoordinatorResponse,
        instructions=prompt,
    )

    for capability in registry.all_capabilities():
        agent_name = capability.agent_name
        vertical = registry.get(agent_name)

        @coordinator.tool(name=f"delegate_to_{agent_name}")
        async def _delegate(ctx: RunContext[CoordinatorDeps], query: str, _v=vertical, _n=agent_name) -> str:
            result = await _v.run(query, usage=ctx.usage)
            return result.output.model_dump_json()

    return coordinator


async def handle(request: CoordinatorRequest) -> CoordinatorResponse:
    """Single entry point for all agent requests."""
    config = get_app_config().agents_coordinator
    registry = get_registry()
    rule_router = RuleBasedRouter(registry.all_capabilities())

    agent_name = rule_router.route(request)

    if agent_name is not None and registry.has(agent_name):
        logger.info("coordinator.routed", agent_name=agent_name, routing_reason="rule")
        vertical = registry.get(agent_name)
        return await vertical.run(request.user_input, usage_limits=_get_limits(config))

    logger.info("coordinator.routing", routing_reason="llm_fallback")
    coordinator = _build_coordinator_agent(config, registry)
    result = await coordinator.run(
        request.user_input,
        deps=CoordinatorDeps(registry=registry, request=request),
        usage_limits=_get_limits(config),
    )
    return result.output


def _get_limits(config: dict) -> UsageLimits:
    limits = config["limits"]
    return UsageLimits(
        request_limit=limits["max_requests_per_task"],
        tool_calls_limit=limits["max_tool_calls_per_task"],
        total_tokens_limit=limits["max_tokens_per_task"],
    )
```

### Rule-Based Router

```python
from modules.agents.coordinator.models import CoordinatorRequest
from modules.agents.vertical.base import AgentCapability


class RuleBasedRouter:
    def __init__(self, capabilities: list[AgentCapability]) -> None:
        self._capabilities = capabilities

    def route(self, request: CoordinatorRequest) -> str | None:
        """Return agent_name if a rule matches, else None (triggers LLM routing)."""
        text = request.user_input.lower()
        for cap in self._capabilities:
            if any(kw in text for kw in cap.keywords):
                return cap.agent_name
        return None
```

### Loop Prevention

Four complementary layers prevent runaway delegation:

1. **UsageLimits** — PydanticAI built-in: `request_limit`, `tool_calls_limit`, `total_tokens_limit` per run
2. **Routing depth counter** — `_depth` incremented on recursive `handle()` calls
3. **Visited-agent set** — prevents cycles in delegation chains
4. **asyncio timeouts** — hard wall-clock backstop on every operation

### Entry Points

The coordinator exposes a single async function: `handle(request: CoordinatorRequest) -> CoordinatorResponse`. All entry points construct a `CoordinatorRequest` and call it.

`CoordinatorRequest` carries gateway context from **[29-multi-channel-gateway.md](29-multi-channel-gateway.md)**:

- `channel` — originating channel (`telegram`, `slack`, `websocket`, `cli`, `tui`, `api`)
- `session_type` — `direct` or `group` (controls session isolation)
- `tool_access_level` — `full`, `sandbox`, or `readonly` (coordinator filters available tools before execution)

When requests arrive through channel adapters (doc 29), the gateway has already enforced security (allowlist, rate limiting, input validation), resolved the session, and set these fields. Direct API callers set them explicitly.

**FastAPI:**

```python
@router.post("/chat")
async def chat(payload: ChatPayload) -> ChatResponse:
    request = CoordinatorRequest(
        user_input=payload.message,
        session_id=payload.session_id,
        user_id=payload.user_id,
        entry_point=EntryPoint.HTTP,
        channel="api",
        session_type="direct",
        tool_access_level="sandbox",
    )
    result = await handle(request)
    return ChatResponse(output=result.output, conversation_id=result.conversation_id)
```

**Taskiq (background):**

```python
@broker.task
async def run_agent_task(task_id: str, user_input: str, session_id: str, user_id: str) -> None:
    request = CoordinatorRequest(
        user_input=user_input,
        session_id=UUID(session_id),
        user_id=user_id,
        entry_point=EntryPoint.TASKIQ,
    )
    result = await handle(request)
    redis = get_redis()
    ttl = get_app_config().agents_coordinator["redis_ttl"]["result"]
    await redis.setex(f"agent:result:{task_id}", ttl, json.dumps({"output": str(result.output)}))
```

**Telegram (aiogram v3):**

```python
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from uuid import uuid5, NAMESPACE_DNS

router = Router(name="agent")

@router.message(Command("ask"))
async def handle_ask(message: Message) -> None:
    user_id = str(message.from_user.id)
    request = CoordinatorRequest(
        user_input=message.text.removeprefix("/ask "),
        session_id=uuid5(NAMESPACE_DNS, user_id),
        user_id=user_id,
        entry_point=EntryPoint.TELEGRAM,
    )
    result = await handle(request)
    await message.answer(str(result.output))
```

**Redis Streams (event-driven):**

```python
import asyncio
import json
from redis.asyncio import Redis
from uuid import UUID

async def consume_agent_stream(redis: Redis, stream_key: str) -> None:
    """Long-running consumer for event-driven agent requests."""
    last_id = "$"
    while True:
        messages = await redis.xread({stream_key: last_id}, block=1000, count=10)
        for _, entries in messages:
            for entry_id, fields in entries:
                data = {k.decode(): v.decode() for k, v in fields.items()}
                request = CoordinatorRequest(
                    user_input=data["user_input"],
                    session_id=UUID(data["session_id"]),
                    user_id=data["user_id"],
                    entry_point=EntryPoint.REDIS_STREAM,
                )
                asyncio.create_task(handle(request))
                last_id = entry_id
```

Start the consumer as a Taskiq task that runs indefinitely, or as a dedicated process entry point.

**WebSocket (real-time streaming):**

```python
from fastapi import WebSocket, WebSocketDisconnect
from uuid import UUID


async def websocket_agent_endpoint(websocket: WebSocket, session_id: str) -> None:
    """WebSocket entry point for real-time agent interaction (TUI, web frontend)."""
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            request = CoordinatorRequest(
                user_input=data["message"],
                session_id=UUID(session_id),
                user_id=data["user_id"],
                entry_point=EntryPoint.WEBSOCKET,
                channel="websocket",
                session_type="direct",
                tool_access_level=data.get("tool_access_level", "sandbox"),
            )

            async with coordinator.run_stream(
                request.user_input,
                deps=CoordinatorDeps(registry=get_registry(), request=request),
                usage_limits=_get_limits(config),
            ) as streamed:
                async for event in streamed.stream_events():
                    if isinstance(event, TextPartDelta):
                        await websocket.send_json({
                            "type": "agent.response.chunk",
                            "text": event.delta,
                        })

            await websocket.send_json({"type": "agent.response.complete"})

    except WebSocketDisconnect:
        pass
```

This is the primary transport for the TUI (**[28-tui-architecture.md](28-tui-architecture.md)**) and the real-time web frontend. Token-by-token streaming via `run_stream()` gives the user immediate feedback as the agent reasons.

**Channel adapters (gateway-mediated):**

When requests arrive through the multi-channel gateway (**[29-multi-channel-gateway.md](29-multi-channel-gateway.md)**), the gateway constructs the `CoordinatorRequest` after enforcing security, resolving the session, and setting `channel`, `session_type`, and `tool_access_level`. Individual channel adapters (Telegram, Slack, Discord) do not call `handle()` directly — they go through the gateway's router, which adds the gateway context and delivers the response back through the originating channel.

---

## Vertical Agent Pattern

### Capability Declaration

```python
from dataclasses import dataclass

@dataclass
class AgentCapability:
    agent_name: str
    description: str          # Used by coordinator agent as routing context
    keywords: list[str]       # Used by rule router for keyword matching
    enabled: bool = True
```

### Dependency Injection

Each vertical agent defines a `@dataclass` for its dependencies. Dependencies are instantiated from the FastAPI DI container and passed at run time.

```python
@dataclass
class ReportAgentDeps:
    report_service: ReportService
    user_service: UserService
    user_id: str
    session_id: str
```

### Implementation

```python
from pathlib import Path
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

_SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "report_agent" / "system.md").read_text()


class ReportOutput(BaseModel):
    summary: str
    report_url: str | None = None


_agent: Agent[ReportAgentDeps, ReportOutput] = Agent(
    model="",  # set from YAML config at registration time
    deps_type=ReportAgentDeps,
    output_type=ReportOutput,
    instructions=_SYSTEM_PROMPT,
)


@_agent.tool
async def fetch_report_data(ctx: RunContext[ReportAgentDeps], report_id: str) -> dict:
    """Fetch structured data for a given report ID."""
    return await ctx.deps.report_service.get_report_data(report_id)


@_agent.tool
async def get_user_permissions(ctx: RunContext[ReportAgentDeps]) -> list[str]:
    """Get the list of report types the current user can access."""
    return await ctx.deps.user_service.get_permissions(ctx.deps.user_id)
```

**Tools are thin adapters.** They contain one call to a service method and the type coercion required to match the LLM schema. No business logic in tools.

**Anti-patterns:**
- Do not call repositories from tools. Tools call services only.
- Do not store service instances as module-level globals. Inject via deps.
- Do not hardcode the model name in agent files. Model comes from YAML config.

---

## Horizontal Middleware Pattern

### Decorator-Based Composition

Horizontal concerns are Python decorators that wrap vertical agent run calls. Every agent passes through the full chain — no exceptions.

```python
import functools
import time
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def with_guardrails(func):
    """Block unsafe input before any LLM call is made."""
    @functools.wraps(func)
    async def wrapper(query: str, *args, **kwargs):
        _check_input(query)
        result = await func(query, *args, **kwargs)
        return result
    return wrapper


def with_cost_tracking(func):
    """Record token usage, compute cost, check budgets after each run."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.monotonic()
        result = await func(*args, **kwargs)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        usage = result.usage()
        cost_usd = _compute_cost(usage, result)
        logger.info(
            "agent.cost",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=round(cost_usd, 6),
            duration_ms=elapsed_ms,
        )
        return result
    return wrapper


def with_memory(redis, memory_service):
    """Load context before run, save results after run."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(query: str, *args, session_id=None, **kwargs):
            history = await _load_session(redis, session_id)
            kwargs["message_history"] = history
            result = await func(query, *args, **kwargs)
            await _save_session(redis, memory_service, session_id, result)
            return result
        return wrapper
    return decorator
```

### Applying Decorators to Agent Runs

```python
@with_guardrails
@with_memory(redis, memory_service)
@with_cost_tracking
async def run_report_agent(query: str, deps: ReportAgentDeps, **kwargs):
    return await _agent.run(query, deps=deps, **kwargs)
```

### Failure Behavior

| Horizontal | Failure Behavior |
|-----------|-----------------|
| Guardrails | Raise exception — abort, no LLM call made |
| Memory (load) | Log error, continue with empty history |
| Memory (save) | Log error, continue — output already returned |
| Cost Tracking | Log error, continue — do not abort on write failure |
| Output Format | Log error, return raw output |

---

## Database Schema

### SQLAlchemy Models

```python
import uuid
from sqlalchemy import String, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from modules.backend.models.base import Base
from modules.backend.core.utils import utc_now


class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)

    messages: Mapped[list["AgentMessage"]] = relationship("AgentMessage", back_populates="conversation")
    runs: Mapped[list["AgentRun"]] = relationship("AgentRun", back_populates="conversation")


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_conversations.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    model_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    conversation: Mapped[AgentConversation] = relationship("AgentConversation", back_populates="messages")


class AgentRun(Base):
    """Core execution record — one row per agent invocation. Maps to AgentTask primitive."""
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_conversations.id"), nullable=False)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    input: Mapped[dict | None] = mapped_column(JSONB)
    output: Mapped[dict | None] = mapped_column(JSONB)
    reasoning: Mapped[dict | None] = mapped_column(JSONB)
    feedback: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    token_input: Mapped[int] = mapped_column(Integer, default=0)
    token_output: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    conversation: Mapped[AgentConversation] = relationship("AgentConversation", back_populates="runs")


class AgentPendingApproval(Base):
    __tablename__ = "agent_pending_approvals"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column()
```

The `parent_run_id` self-referential FK on `agent_runs` traces the full delegation chain (coordinator -> specialist -> worker), enabling cost attribution and debugging per delegation path.

### Redis Key Patterns

All TTL values come from `config/agents/coordinator.yaml` under `redis_ttl`.

| Key Pattern | Type | TTL Config Key | Purpose |
|------------|------|----------------|---------|
| `agent:session:{session_id}` | JSON string | `redis_ttl.session` | Short-term conversation history |
| `agent:approval:{approval_id}` | JSON string | `redis_ttl.approval` | Pending HITL approval state |
| `agent:lock:{conversation_id}` | string | `redis_ttl.lock` | Distributed lock (prevent concurrent runs) |
| `agent:result:{task_id}` | JSON string | `redis_ttl.result` | Async task result storage |

### Idempotency and Checkpoint/Resume

Write a checkpoint to `agent_checkpoints` before and after every tool call. On resume, load the latest incomplete checkpoint and replay from that state. Use the `conversation_id` as the idempotency key — a second request with the same `conversation_id` and identical input returns the stored result without re-running the agent.

```python
async def write_checkpoint(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    agent_name: str,
    state: dict,
) -> None:
    """Persist execution state for resume after interruption."""
    from modules.agents.models import AgentCheckpoint

    checkpoint = AgentCheckpoint(
        conversation_id=conversation_id,
        agent_name=agent_name,
        state=state,
        is_complete=False,
    )
    session.add(checkpoint)
    await session.commit()
```

Add an `AgentCheckpoint` model alongside the other models in the Database Schema section:

```python
class AgentCheckpoint(Base):
    __tablename__ = "agent_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_conversations.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_complete: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
```

---

## Execution Patterns

### Synchronous (HTTP)

Standard request-response. Use for interactions with latency under 30 seconds.

```
POST /api/v1/agents/chat → handle(request) → agent.run() → return JSON
```

### Asynchronous (Taskiq)

For long-running agent tasks. Returns immediately with a task ID.

```
POST /api/v1/agents/chat/async → enqueue run_agent_task → return {"task_id": "..."}
GET /api/v1/agents/results/{task_id} → read from Redis → return result or 202
```

### Streaming (SSE)

Use PydanticAI's `run_stream()` for token-by-token delivery:

```python
from fastapi.responses import StreamingResponse
from pydantic_ai.messages import TextPartDelta

@router.post("/chat/stream")
async def chat_stream(payload: ChatPayload) -> StreamingResponse:
    async def generate():
        async with _agent.run_stream(payload.message, deps=deps) as streamed:
            async for event in streamed.stream_events():
                if isinstance(event, TextPartDelta):
                    yield f"data: {event.delta}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Streaming (Built-in Adapters)

PydanticAI ships with protocol-specific adapters for chat UIs. Use these instead of manual SSE when integrating with Vercel AI SDK or AG-UI compatible frontends:

```python
from starlette.requests import Request
from starlette.responses import Response
from pydantic_ai import Agent
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

agent = Agent('openai:gpt-4o', instructions='Helpful assistant.')

@router.post("/chat/vercel")
async def chat_vercel(request: Request) -> Response:
    """Vercel AI SDK compatible streaming endpoint."""
    return await VercelAIAdapter.dispatch_request(request, agent=agent)
```

The `AGUIAdapter` and `AGUIApp` provide AG-UI protocol support (CopilotKit and similar frameworks). For custom streaming, `agent.run_stream()` returns an async context manager with `.stream_text(delta=True)` for direct SSE integration.

### Scheduled (Taskiq Cron)

```python
@broker.task
async def scheduled_report_generation() -> None:
    request = CoordinatorRequest(
        user_input="Generate daily summary report",
        session_id=SYSTEM_SESSION_ID,
        user_id="system",
        entry_point=EntryPoint.TASKIQ,
    )
    await handle(request)
```

---

## Configuration

### Agent YAML

Agent names follow the `{category}.{name}` convention. The config file lives at `config/agents/{category}/{name}.yaml`.

```yaml
# config/agents/domain/reporting/agent.yaml
# =============================================================================
# Available options:
#   agent_name      - Unique agent identifier (string, format: category.name)
#   description     - Agent description for routing (string)
#   enabled         - Enable/disable without code deployment (boolean)
#   model           - LLM model identifier (string, provider:model format)
#   max_budget_usd  - Maximum cost per task in USD (decimal)
#   keywords        - Keywords for rule-based routing (list of strings)
#   tools           - Registered tool names (list of strings)
#   max_input_length - Maximum input character count (integer)
# =============================================================================

agent_name: domain.reporting.agent
description: "Generates, retrieves, and summarises reports"
enabled: true
model: anthropic:claude-sonnet-4-20250514
max_budget_usd: 0.50
max_input_length: 32000
keywords:
  - report
  - generate report
  - summarise
  - summary
tools:
  - fetch_report_data
  - get_user_permissions
```

### Coordinator YAML

```yaml
# config/agents/coordinator.yaml
# =============================================================================
# Available options:
#   routing           - Routing configuration (object)
#     strategy        - Routing strategy (string: rule|llm|hybrid)
#     llm_model       - Model for LLM-based routing (string)
#     fallback_agent  - Default agent when routing fails (string)
#     max_routing_depth - Maximum delegation depth (integer)
#   limits            - Budget and safety limits (object)
#     max_requests_per_task    - Max LLM calls per task (integer)
#     max_tool_calls_per_task  - Max tool invocations per task (integer)
#     max_tokens_per_task      - Max tokens per task (integer)
#     max_cost_per_plan        - Max USD per plan (decimal)
#     max_cost_per_user_daily  - Max USD per user per day (decimal)
#     task_timeout_seconds     - Wall-clock timeout per task (integer)
#     plan_timeout_seconds     - Wall-clock timeout per plan (integer)
#   redis_ttl         - Redis key TTLs in seconds (object)
#     session         - Session history TTL (integer)
#     approval        - Pending approval TTL (integer)
#     lock            - Distributed lock TTL (integer)
#     result          - Async result TTL (integer)
#   guardrails        - Input validation settings (object)
#     max_input_length - Maximum input character count (integer)
#     injection_patterns - Regex patterns to block (list of strings)
#   approval          - HITL approval settings (object)
#     poll_interval_seconds - Polling interval (integer)
#     timeout_seconds       - Max wait for approval (integer)
# =============================================================================

routing:
  strategy: hybrid
  llm_model: anthropic:claude-haiku-4.5
  fallback_agent: fallback_agent
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

### Feature Flags

Set `enabled: false` in any agent YAML to disable it without code deployment. The registry skips disabled agents.

---

## Session-Aware Agent Invocation (Doc 31)

When the project adopts `31-event-session-architecture.md`, agent invocation changes from direct `run()` calls to coordinator-mediated streaming.

### Primary Path: `run_stream()` via Coordinator

All interactive agent invocations go through the streaming coordinator, which calls `agent.run_stream()` internally:

```python
# modules/backend/agents/coordinator/handle.py
from pydantic_ai import Agent

async def handle(session_id: str, message: str) -> AsyncIterator[Event]:
    session = await session_service.get(session_id)
    agent = agent_router.resolve(message, session)
    deps = AgentDeps(session=session, db=session.db)

    async with agent.run_stream(message, deps=deps) as stream:
        async for chunk in stream.stream_text(delta=True):
            yield AgentResponseChunkEvent(session_id=session_id, content=chunk)

    yield AgentResponseCompleteEvent(session_id=session_id, content=stream.result.data)
```

### When to Use Direct `run()`

Direct `agent.run()` is still appropriate for:
- Background tasks that do not have an interactive session (Taskiq jobs)
- Batch processing where streaming is irrelevant
- Unit tests where you need a synchronous result

Direct `run()` bypasses session cost tracking, event emission, and approval gates. Use it only when these features are not needed.

### Extended AgentDeps

Add an optional `Session` field to the dependency container:

```python
# modules/backend/agents/dependencies.py
from dataclasses import dataclass
from modules.backend.services.base import BaseService

@dataclass
class AgentDeps:
    db: AsyncSession
    session: Session | None = None  # Present for interactive, None for batch

    @property
    def note_service(self) -> NoteService:
        return NoteService(self.db)

    @property
    def cost_remaining(self) -> float | None:
        return self.session.cost_budget_remaining if self.session else None
```

Tools that need session context access it through `ctx.deps.session`. Tools that don't need it are unaffected — `session` defaults to `None`.

See `31-event-session-architecture.md`, Section 3 (Streaming Coordinator) for the complete `handle()` implementation and agent routing.

---

## Testing

### CI Guardrail

```python
# tests/conftest.py
from pydantic_ai import models
models.ALLOW_MODEL_REQUESTS = False
```

Any test that accidentally calls a real LLM fails immediately. This is a CI/CD guardrail that prevents cost leaks.

### Unit Testing with TestModel

`TestModel` generates deterministic, schema-valid responses without any LLM. It calls all registered tools to verify they work:

```python
import pytest
from unittest.mock import AsyncMock
from pydantic_ai.models.test import TestModel
from pydantic_ai import capture_run_messages
from modules.agents.vertical.report_agent import _agent, ReportOutput
from modules.agents.deps.report_agent import ReportAgentDeps


@pytest.fixture
def mock_deps() -> ReportAgentDeps:
    report_svc = AsyncMock()
    report_svc.get_report_data.return_value = {"title": "Q1 Summary", "rows": 42}
    user_svc = AsyncMock()
    user_svc.get_permissions.return_value = ["view_reports"]
    return ReportAgentDeps(
        report_service=report_svc, user_service=user_svc,
        user_id="user_123", session_id="sess_abc",
    )


@pytest.mark.asyncio
async def test_report_agent_output_schema(mock_deps: ReportAgentDeps) -> None:
    with _agent.override(model=TestModel()):
        result = await _agent.run("Summarise all reports", deps=mock_deps)
    assert isinstance(result.output, ReportOutput)
    mock_deps.report_service.get_report_data.assert_awaited()


@pytest.mark.asyncio
async def test_report_agent_tool_calls(mock_deps: ReportAgentDeps) -> None:
    with _agent.override(model=TestModel()):
        with capture_run_messages() as messages:
            await _agent.run("Fetch report R-42", deps=mock_deps)
    assert any(hasattr(m, "parts") for m in messages)
```

### Scripted Testing with FunctionModel

`FunctionModel` gives full control — write a Python function that returns whatever response your test scenario requires:

```python
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart


def mock_routing(messages, info):
    user_msg = messages[0].parts[-1].content.lower()
    if "billing" in user_msg:
        return ModelResponse(parts=[ToolCallPart("handle_billing", {"query": user_msg})])
    return ModelResponse(parts=[TextPart("How can I help?")])


@pytest.mark.asyncio
async def test_coordinator_routes_billing():
    with coordinator.override(model=FunctionModel(mock_routing)):
        result = await coordinator.run("I have a billing question")
    assert "billing" in str(result.output).lower()
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_chat_endpoint(client: AsyncClient) -> None:
    with report_agent.override(model=TestModel()):
        response = await client.post(
            "/api/v1/agents/chat",
            json={"message": "Generate a report summary", "session_id": "...", "user_id": "test"},
        )
    assert response.status_code == 200
    assert "output" in response.json()
```

### Testing Pyramid

| Layer | Purpose | Tooling | When |
|-------|---------|---------|------|
| Deterministic | Unit tests with TestModel/FunctionModel | pytest + PydanticAI test models | Every commit (CI) |
| Record/Replay | Captured real LLM sessions replayed | VCR fixtures | Every commit (CI) |
| Probabilistic | Benchmark suites measuring success rates | pydantic-evals | On-demand |
| Judgment | LLM-as-judge with rubrics | Custom evaluation | On-demand |

---

## Observability

### structlog Integration

Bind agent context at the coordinator level:

```python
import structlog.contextvars

structlog.contextvars.bind_contextvars(
    conversation_id=str(request.conversation_id),
    session_id=str(request.session_id),
    user_id=request.user_id,
    entry_point=request.entry_point.value,
    agent_name=agent_name,
)
```

All downstream log calls automatically include these fields.

### What to Log at Each Layer

| Layer | Event Key | Required Fields |
|-------|-----------|-----------------|
| Coordinator | `coordinator.routing` | session_id, entry_point |
| Coordinator | `coordinator.routed` | agent_name, routing_reason, duration_ms |
| Guardrails | `guardrails.violation` | pattern, user_id |
| Cost | `agent.cost` | agent_name, input_tokens, output_tokens, cost_usd |
| Memory | `agent.memory.load` | session_id, history_length |
| Memory | `agent.memory.save` | session_id, conversation_id |
| Vertical agent | `agent.run.start` | agent_name, model |
| Vertical agent | `agent.run.complete` | agent_name, duration_ms |
| Tool | `agent.tool.call` | tool_name, agent_name |
| Tool | `agent.tool.result` | tool_name, duration_ms, success |

Agent logs are written to `logs/system.jsonl` with `source="agents"` per **12-observability.md**.

---

## Security

### Human-in-the-Loop Approval Gates

```python
import asyncio
import json
import uuid
from modules.backend.core.config import get_app_config


async def request_approval(
    redis,
    session,
    conversation_id: uuid.UUID,
    agent_name: str,
    action: dict,
    requested_by: str,
) -> bool:
    """Pause execution and wait for human approval. Returns True if approved."""
    config = get_app_config().agents_coordinator["approval"]
    approval_id = uuid.uuid4()
    ttl = get_app_config().agents_coordinator["redis_ttl"]["approval"]

    pending = AgentPendingApproval(
        id=approval_id,
        conversation_id=conversation_id,
        agent_name=agent_name,
        action=action,
        requested_by=requested_by,
    )
    session.add(pending)
    await session.commit()

    redis_key = f"agent:approval:{approval_id}"
    await redis.setex(redis_key, ttl, json.dumps({"status": "pending"}))

    elapsed = 0
    while elapsed < config["timeout_seconds"]:
        raw = await redis.get(redis_key)
        if raw:
            data = json.loads(raw)
            if data["status"] == "approved":
                return True
            if data["status"] == "rejected":
                return False
        await asyncio.sleep(config["poll_interval_seconds"])
        elapsed += config["poll_interval_seconds"]

    return False
```

### Tool-Level Access Control

Define allowed tools per agent in `config/agents/coordinator.yaml`:

```yaml
tool_access:
  report_agent:
    - fetch_report_data
    - get_user_permissions
  fallback_agent: []
```

The registry validates tool declarations against this allowlist at registration time.

### Prompt Injection Mitigation

- User input is always placed in the `user` role — never interpolated into the system prompt
- Guardrails decorator pattern-matches for injection attempts before the LLM is invoked
- Injection patterns are configured in YAML, not hardcoded
- System prompts are loaded from static Markdown files at startup
- The coordinator does not pass raw user input to the routing prompt

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/agents/chat` | Synchronous agent interaction |
| `POST` | `/api/v1/agents/chat/async` | Submit for background processing, returns task_id |
| `POST` | `/api/v1/agents/chat/stream` | SSE streaming response |
| `GET` | `/api/v1/agents/results/{task_id}` | Retrieve async task result |
| `GET` | `/api/v1/agents/conversations/{id}` | Conversation history with reasoning |
| `POST` | `/api/v1/agents/approvals/{id}` | Approve/reject pending HITL action |
| `POST` | `/api/v1/agents/cancel` | Kill switch |
| `GET` | `/api/v1/agents/costs` | Cost reporting |
| `GET` | `/api/v1/agents/registry` | List available agents and capabilities |

---

## Adding a New Agent (Walkthrough)

Adding `data.analysis` (a data-category agent) from zero to working:

**1. Create deps** — `modules/agents/deps/data/analysis.py`:

```python
@dataclass
class DataAnalysisAgentDeps:
    dataset_service: DatasetService
    user_service: UserService
    user_id: str
    session_id: str
```

**2. Create prompt** — `modules/agents/prompts/data/analysis/system.md`:

```markdown
You are a data analysis agent. You help users explore, summarise, and interpret datasets.

Rules:
- Always explain what the data contains before interpreting it.
- If a dataset does not exist, say so clearly. Do not fabricate values.
- Return structured output using the DataAnalysisOutput schema.
```

**3. Create agent** — `modules/agents/vertical/data/analysis/agent.py`:

```python
from pydantic_ai import Agent, RunContext

_SYSTEM_PROMPT = (Path(__file__).parent.parent.parent.parent / "prompts" / "data" / "analysis" / "system.md").read_text()

class DataAnalysisOutput(BaseModel):
    summary: str
    columns: list[str]
    row_count: int
    insights: list[str]

_agent: Agent[DataAnalysisAgentDeps, DataAnalysisOutput] = Agent(
    model="",
    deps_type=DataAnalysisAgentDeps,
    output_type=DataAnalysisOutput,
    instructions=_SYSTEM_PROMPT,
)

@_agent.tool
async def fetch_dataset(ctx: RunContext[DataAnalysisAgentDeps], dataset_id: str) -> dict:
    """Fetch a dataset by ID and return its schema and a sample of rows."""
    return await ctx.deps.dataset_service.get_dataset(dataset_id)
```

**4. Create config** — `config/agents/data/analysis/agent.yaml`:

```yaml
# =============================================================================
# Available options:
#   agent_name      - Unique agent identifier (string, format: category.name)
#   ...
# =============================================================================

agent_name: data.analysis.agent
description: "Analyses datasets, computes statistics, and surfaces insights"
enabled: true
model: anthropic:claude-sonnet-4-20250514
max_budget_usd: 1.00
max_input_length: 32000
keywords:
  - analyse
  - analysis
  - dataset
  - statistics
  - data
tools:
  - fetch_dataset
  - get_column_stats
```

**5. Register** — add to `modules/agents/startup.py` registration loop.

**6. Write tests** — `tests/agents/vertical/test_data_analysis.py`:

```python
@pytest.mark.asyncio
async def test_data_analysis_output_schema(mock_deps) -> None:
    with _agent.override(model=TestModel()):
        result = await _agent.run("Analyse dataset DS-99", deps=mock_deps)
    assert isinstance(result.output, DataAnalysisOutput)
    mock_deps.dataset_service.get_dataset.assert_awaited()
```

**7. Write integration test** — `tests/agents/integration/test_data_analysis_flow.py`:

```python
@pytest.mark.asyncio
async def test_data_analysis_end_to_end(client: AsyncClient) -> None:
    with data_agent.override(model=TestModel()):
        response = await client.post(
            "/api/v1/agents/chat",
            json={"message": "Analyse dataset DS-99", "session_id": "...", "user_id": "test"},
        )
    assert response.status_code == 200
```

No coordinator changes needed. The registry auto-discovers the new agent by scanning for `agent.yaml` files recursively under `config/agents/`.

---

## Anti-Patterns

| Anti-pattern | Why prohibited |
|-------------|---------------|
| Tool calls a repository directly | Bypasses service layer; breaks separation of concerns |
| Agent calls another agent without the coordinator | Bypasses routing, observability, loop prevention, and horizontal composition |
| Business logic inside tool functions | Tools are thin adapters; business logic in tools is untestable without agent runtime |
| Model name hardcoded in agent file | Model is configuration; hardcoding prevents swaps without code changes |
| User input interpolated into system prompt | Enables prompt injection; user input is always in the `user` role |
| Skipping horizontal decorators for "simple" agents | All agents need cost tracking, guardrails, and observability — no exceptions |
| Storing conversation history in Redis indefinitely | Redis is ephemeral; use TTL and flush to PostgreSQL via Memory decorator |
| Running LLM-based routing for every request | Rules first, LLM fallback only — avoids unnecessary latency and cost |
| Synchronous blocking calls in async agent tools | Blocks the event loop; use `asyncio.to_thread()` for CPU-bound work |
| Hardcoded TTLs, cost rates, or timeouts in code | All operational parameters come from YAML config |
| Agent name without category prefix or entity suffix (e.g., `health_agent`) | All agents use `{category}.{name}.agent` format (e.g., `system.health.agent`) — see "Agent Naming Convention" |

---

## Phase-by-Phase Implementation Checklist

### Prerequisites
- [ ] 08-llm-integration.md adopted
- [ ] 06-event-architecture.md adopted
- [ ] PydanticAI installed (`pip install pydantic-ai`)
- [ ] 25-agentic-architecture.md reviewed (conceptual foundation)

### Phase 1: Execute
- [ ] Create `modules/agents/` directory structure
- [ ] Implement coordinator Agent with hybrid routing
- [ ] Implement `VerticalAgentRegistry`
- [ ] Implement horizontal decorators (guardrails, cost, output format)
- [ ] Create database migration for agent tables
- [ ] Create at least one vertical agent with tools
- [ ] Create coordinator YAML config with limits
- [ ] Implement FastAPI endpoints (chat, cancel, costs, registry)
- [ ] Implement kill switch (API + CLI)
- [ ] Set up `ALLOW_MODEL_REQUESTS = False` in test conftest
- [ ] Write unit tests with TestModel
- [ ] Write integration tests for routing
- [ ] Add `agents` log source to logging config
- [ ] Configure budget limits

### Phase 2: Plan
- [ ] Implement plan creation in coordinator (multi-step decomposition)
- [ ] Implement step sequencing with dependency tracking
- [ ] Implement shared context between plan steps
- [ ] Implement context summarization (cheap model for compression)
- [ ] Implement confidence signaling in routing decisions
- [ ] Write tests for multi-step plans

### Phase 3: Remember
- [ ] Enable pgvector extension on PostgreSQL
- [ ] Implement Memory decorator with semantic retrieval
- [ ] Implement memory lifecycle (access counts, archival, summarization)
- [ ] Add memory inspection API endpoints

### Phase 4: Learn
- [ ] Implement feedback collection (human ratings, automated checks)
- [ ] Link feedback to memory entries with quality scores
- [ ] Implement outcome-weighted retrieval
- [ ] Implement performance-based routing in coordinator

### Phase 5: Autonomy
- [ ] Implement agent proposal mechanism
- [ ] Implement tiered delegation (agent-as-tool with `usage=ctx.usage`)
- [ ] Implement trust levels per agent based on performance history
- [ ] Implement self-evaluation agent

---

## Related Documentation

- [25-agentic-architecture.md](25-agentic-architecture.md) — **Conceptual architecture** (phases, principles, patterns, primitive)
- [29-multi-channel-gateway.md](29-multi-channel-gateway.md) — Multi-channel delivery, session management, channel adapters, WebSocket real-time push
- [Why PydanticAI is the right agent framework](../../98-research/08-Why%20PydanticAI%20is%20the%20right%20agent%20framework%20for%20your%20FastAPI%20stack.md) — Framework selection rationale
- [Multi-agent systems on FastAPI](../../98-research/03-Multi-agent%20systems%20on%20FastAPI-%20a%20prescriptive%20reference%20architecture.md) — PydanticAI pattern reference
- [08-llm-integration.md](08-llm-integration.md) — LLM provider interface, cost tracking, prompt management
- [06-event-architecture.md](06-event-architecture.md) — Redis Streams for agent events
- [19-background-tasks.md](19-background-tasks.md) — Taskiq for scheduled agent work
- [12-observability.md](12-observability.md) — Logging standards
- [09-authentication.md](09-authentication.md) — RBAC for agent API access
- [04-module-structure.md](04-module-structure.md) — Module boundaries and communication
- [31-event-session-architecture.md](31-event-session-architecture.md) — Session-aware agent invocation, streaming coordinator, event-driven interaction model
