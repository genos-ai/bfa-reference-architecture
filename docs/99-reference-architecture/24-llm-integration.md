# 24 - LLM Integration (Optional Module)

*Version: 2.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 2.0.0 (2026-02-18): Added tool/function calling, LLM provider interface, model version tracking, fallback model configuration, expanded provider guidance, updated cost tracking fields, added agent prompt paths; replaced multi-agent stub with reference to 40-agentic-architecture.md
- 1.0.0 (2025-01-27): Initial generic LLM integration standard

---

## Module Status: Optional

This module is **optional**. Adopt when your project:
- Integrates AI/LLM capabilities
- Uses generative AI for content creation
- Implements AI agents or assistants
- Requires natural language processing

For applications without AI features, this module is not required.

For **agentic AI systems** (autonomous agents, orchestration, tool use, persistent memory), also adopt **40-agentic-architecture.md** which builds on this module.

---

## Context

LLM providers have incompatible APIs, different pricing models, varying reliability for tool calling, and frequently change their model offerings. Applications that call provider APIs directly end up with scattered, inconsistent integration code that is expensive to maintain and impossible to switch between providers.

This module solves that by defining a centralized LLM service layer with a common `LLMProvider` interface. All LLM calls go through this abstraction, which handles provider-specific details (authentication, request format, response parsing), model version tracking, fallback configuration, and cost recording. The abstraction boundary sits between the application's business logic and the provider API — not inside a generic utility.

Tool/function calling is standardized with explicit limits (5 calls per turn, 10 rounds maximum) and timeout enforcement because unconstrained tool loops are the primary failure mode in LLM-powered applications. Prompts live in YAML configuration files rather than code, enabling iteration on prompts without code deployments. Cost tracking records every call with enough detail (model, tokens, cost, duration, user, task type) to attribute spend and detect anomalies. For simple LLM use cases (summarization, classification, extraction), this module is sufficient on its own. For agentic systems that reason, plan, and use tools autonomously, the agentic architecture (40) builds on top of it.

---

## Provider Selection

### Choosing a Provider

Select an LLM provider based on:
- Task complexity requirements
- Tool/function calling reliability
- Context window needs
- Cost constraints
- Latency requirements
- Data privacy requirements

### Provider Comparison

| Provider | Tool Calling Reliability | Context Window | Strengths | Considerations |
|----------|--------------------------|----------------|-----------|----------------|
| Anthropic (Claude) | Tier 1 (90%+ BFCL) | 200K tokens | Reasoning, safety, coding (72.5% SWE-bench) | Cost at scale |
| OpenAI (GPT-4o/4.1) | Tier 1 (90%+) | 128K-1M tokens | Mature ecosystem, structured outputs, broad capabilities | Rate limits, pricing |
| Google (Gemini 2.5) | Tier 1-2 | 1-2M tokens | Multimodal, thinking capabilities, massive context | Newer ecosystem |
| Meta (Llama 3.1) | Tier 3 (70-80%) | 128K tokens | Open-source, no API costs, full customization | Self-hosting required, variable quality |
| Mistral | Tier 3 (70-80%) | 32-128K tokens | European compliance, parallel function calling | Smaller community |
| Local models (Ollama) | Varies | Model-dependent | Privacy, no API costs, offline capability | Hardware requirements, lower reliability |

### Model Tiers

Most providers offer model tiers. Match tier to task complexity:

| Tier | Reliability | Use For | Example Models |
|------|-------------|---------|----------------|
| Fast/Small | Variable | Classification, simple extraction, formatting | GPT-4o mini, Claude 3.5 Haiku, Ministral 3B |
| Standard | 80-90% | Code generation, analysis, conversations, tool use | GPT-4o, Claude Sonnet, Gemini 2.0 Flash |
| Advanced | 90%+ | Complex reasoning, multi-step problems, orchestration | GPT-4.1, Claude Opus 4.1, Gemini 2.5 Pro |

**Critical insight for tool-heavy workloads:** Multi-step tool scenarios achieve only 50-70% success rates even with Tier 1 models. Error handling and retry mechanisms are essential, not optional. Design for failure.

### Model Selection by Use Case

| Use Case | Recommended Tier | Rationale |
|----------|------------------|-----------|
| Simple classification/extraction | Fast/Small | Cost-effective, low latency |
| Single-turn tool use | Standard | Good balance of reliability and cost |
| Multi-step agent workflows | Advanced | Highest tool-calling reliability |
| Orchestrator/planner decisions | Advanced | Needs strong reasoning for task decomposition |
| Context summarization | Fast/Small | Straightforward task, minimize cost |
| Code generation | Standard-Advanced | Depends on code complexity |
| Content generation | Standard | Good quality at reasonable cost |

---

## Integration Architecture

### LLM Service Layer

All LLM calls go through a centralized service:

Responsibilities:
- Model selection and fallback routing
- Prompt construction from templates
- Tool/function definition injection
- API call execution with timeout enforcement
- Response parsing (text and tool calls)
- Model version recording
- Cost computation and tracking
- Error handling, retry, and fallback

No direct provider API calls outside this service.

### LLM Provider Interface

All providers implement a common interface. This abstraction enables model switching, fallback routing, and consistent cost tracking regardless of the underlying API.

```python
class LLMProvider:
    """Common interface for all LLM providers."""

    async def complete(
        self,
        messages: list[Message],
        model: str,
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        """Send a completion request."""


@dataclass
class Message:
    role: str                       # "system", "user", "assistant", "tool"
    content: str
    tool_call_id: str | None = None # For tool result messages


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict                # JSON Schema for tool parameters


@dataclass
class ToolCall:
    id: str                         # Unique ID for this tool invocation
    name: str                       # Tool function name
    arguments: dict                 # Parsed arguments


@dataclass
class LLMResponse:
    content: str | None             # Text response (None if tool call only)
    tool_calls: list[ToolCall]      # Requested tool invocations (empty if text only)
    model: str                      # Exact model version used
    usage: TokenUsage               # Token counts
    cost: Decimal                   # Computed cost in USD
    duration_ms: int                # Call duration
    raw_response: dict              # Full provider response (for audit/debugging)


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
```

**Provider implementations** (e.g., `AnthropicProvider`, `OpenAIProvider`, `OllamaProvider`) translate between this interface and each provider's specific API format. The calling code never interacts with provider-specific APIs.

### Model Version Tracking

Every LLM call records the **exact model identifier** returned by the provider, not just the requested model alias. Models change behavior across versions without notice.

```python
# What you request:
model = "claude-sonnet-4-20250514"

# What gets recorded:
response.model = "claude-sonnet-4-20250514"  # Exact version from API response
```

This is stored on every record that involves an LLM call (cost tracking table, agent task records if using 40-agentic-architecture.md). It enables:
- Debugging behavior changes ("it worked last week — what model version was that?")
- Reproducibility analysis
- Model drift detection in evaluation runs

### Fallback Model Configuration

Each model configuration can specify a fallback. When the primary model fails (rate limit, timeout, outage), the provider layer tries the fallback automatically.

```yaml
# config/settings/llm.yaml
models:
  default:
    provider: anthropic
    model: claude-sonnet-4-20250514
    fallback:
      provider: openai
      model: gpt-4o

  fast:
    provider: anthropic
    model: claude-3-5-haiku-20241022
    fallback:
      provider: openai
      model: gpt-4o-mini
```

**Fallback rules:**
- Fallback is tried only for transient errors (rate limit, timeout, 5xx). Not for permanent errors (invalid key, malformed request).
- Maximum one fallback attempt per call (no fallback chains).
- The fallback model is recorded in the response: `response.model` reflects whichever model actually answered.
- Fallback events are logged at WARNING level with both the primary and fallback model identifiers.
- The caller is never silently given a different model — the response always indicates which model was used.

### Request Flow

1. Application code calls LLM service with task type, inputs, and optional tool definitions
2. Service selects appropriate model (from config or caller specification)
3. Service constructs prompt from template + inputs
4. Service injects tool definitions if provided
5. Service calls provider API with timeout enforcement
6. If call fails with transient error, retry (up to 3 times with backoff)
7. If all retries fail and fallback configured, try fallback model
8. Service parses response (text content and/or tool calls)
9. Service validates response against expected schema (if specified)
10. Service records: model version, tokens, computed cost, duration
11. Service returns `LLMResponse` to caller

### Timeout Configuration

Configure timeouts based on model characteristics:

| Model Tier | Suggested Timeout |
|------------|-------------------|
| Fast/Small | 30 seconds |
| Standard | 60 seconds |
| Advanced | 120 seconds |

Timeouts are per-request. Long operations should be broken into multiple calls.

---

## Tool / Function Calling

### Overview

Tool calling (also known as function calling) allows the LLM to request execution of external functions. The LLM does not execute tools directly — it returns a structured request that the application executes, then feeds the result back.

This is the foundation for agentic behavior. Without tool calling, LLMs can only produce text. With tool calling, they can search the web, read files, execute code, query databases, and interact with external systems.

### Tool Definition Format

Tools are described to the LLM using JSON Schema:

```python
tool = ToolDefinition(
    name="web_search",
    description="Search the web for current information on a topic",
    parameters={
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return",
                "default": 5
            }
        }
    }
)
```

**Tool description quality directly affects reliability.** Vague descriptions lead to incorrect tool selection. Be specific about what the tool does, what inputs it expects, and what it returns.

### Tool Call Flow

```
1. Application sends messages + tool definitions to LLM
2. LLM responds with tool_calls (instead of or alongside text)
3. Application executes each tool call
4. Application sends tool results back as messages (role="tool")
5. LLM processes results and either:
   a. Makes more tool calls (loop back to step 3)
   b. Returns final text response
```

### Tool Call Limits

To prevent runaway tool usage:

| Limit | Default | Purpose |
|-------|---------|---------|
| Max tool calls per LLM turn | 5 | Prevents single response from triggering excessive calls |
| Max tool call rounds | 10 | Prevents infinite tool call loops |
| Tool execution timeout | 60 seconds | Per individual tool execution |

If limits are exceeded, the loop terminates and returns whatever results are available.

### Provider Differences

Tool calling implementation varies by provider. The LLM provider interface abstracts these differences:

| Provider | Tool Call Format | Parallel Calls | Strict Schema |
|----------|-----------------|----------------|---------------|
| Anthropic | `tool_use` content blocks | Yes | No |
| OpenAI | `tool_calls` in response | Yes | Yes (structured outputs) |
| Google | `functionCall` parts | Yes | Yes |
| Ollama/Local | Varies by model | Model-dependent | No |

The provider implementations handle format translation. Calling code works with the standard `ToolCall` and `ToolDefinition` types regardless of provider.

---

## Prompt Management

### Prompt Storage

Store prompts in configuration files, not code:

```
config/
└── prompts/
    ├── tasks/                          # Task-specific prompts
    │   ├── summarization.yaml
    │   ├── classification.yaml
    │   └── extraction.yaml
    ├── agents/                         # Agent system prompts (used by 40-agentic-architecture.md)
    │   ├── orchestrator.yaml
    │   ├── general_assistant.yaml
    │   └── code_reviewer.yaml
    └── shared/
        └── common_instructions.yaml
```

### Prompt Structure

Each prompt file contains:
- System prompt (role and behavior)
- Task-specific instructions
- Input placeholders
- Output format specification
- Example inputs/outputs (for few-shot)

### Prompt Versioning

Prompt files are version controlled. Changes to prompts require:
1. Version increment in file
2. Testing against evaluation set
3. Review before deployment

### Variable Injection

Prompts use placeholder syntax: `{{variable_name}}`

Variables injected at runtime:
- User input
- Context data
- Configuration values

No string concatenation for prompt construction. Always use template engine.

---

## Context Management

### Context Window Strategy

Large context windows are available but costs scale with token usage:

Strategy:
- Include only relevant context
- Summarize long documents
- Use retrieval to find relevant snippets
- Truncate conversation history intelligently

### Context Priority

When context must be reduced, prioritize:
1. Current user request (never truncate)
2. Most recent conversation turns
3. Directly relevant documents
4. Related context
5. Historical context (oldest first to remove)

---

## Response Handling

### Structured Outputs

Request structured outputs (JSON) when processing results programmatically:
- Specify exact schema in prompt
- Use JSON mode if available
- Validate response against schema
- Handle parse failures gracefully

### Response Validation

All LLM responses validated before use:
- Schema validation for structured outputs
- Sanity checks for generated code
- Safety checks for user-facing content

Invalid responses:
- Log full response for debugging
- Retry with clarified prompt (once)
- Fall back to error state if retry fails

### Streaming Responses

For user-facing chat:
- Stream response tokens as they arrive
- Display incremental output
- Allow cancellation mid-stream

For background processing:
- Wait for complete response
- No streaming (simpler error handling)

---

## Cost Management

### Cost Tracking

Every LLM call records:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique record identifier |
| `model` | string | Exact model version used (from provider response) |
| `provider` | string | Provider name (anthropic, openai, google, local) |
| `input_tokens` | int | Input tokens consumed |
| `output_tokens` | int | Output tokens generated |
| `cost_usd` | decimal | Computed cost in USD |
| `duration_ms` | int | Call duration in milliseconds |
| `user_id` | UUID | User who initiated the call |
| `task_type` | string | What the call was for (classification, generation, agent_work, etc.) |
| `tool_calls_count` | int | Number of tool calls in this response |
| `fallback_used` | boolean | Whether this used a fallback model |
| `created_at` | datetime | Timestamp (UTC, timezone-naive) |

Storage: PostgreSQL table (`llm_usage`). Queryable for billing, analysis, and optimization.

**Cost computation:** The service maintains a pricing table per model (input price per 1K tokens, output price per 1K tokens). This table is in YAML config, not hardcoded. Update when providers change pricing.

```yaml
# config/settings/llm_pricing.yaml
pricing:
  anthropic/claude-sonnet-4-20250514:
    input_per_1k: 0.003
    output_per_1k: 0.015
  openai/gpt-4o:
    input_per_1k: 0.0025
    output_per_1k: 0.01
  openai/gpt-4o-mini:
    input_per_1k: 0.00015
    output_per_1k: 0.0006
```

### Cost Controls

Implement limits at multiple levels:
- Per-request token limit
- Per-user daily/monthly limit
- Per-project budget
- System-wide circuit breaker

Exceeding limits:
- Soft limit: Warning, continue
- Hard limit: Reject request with clear message

### Cost Optimization

- Use smaller models for simple tasks
- Cache common prompts
- Summarize long contexts
- Batch related requests when possible

---

## Error Handling

### Retry Strategy

Transient errors (rate limits, timeouts, server errors):
- Retry with exponential backoff
- Maximum 3 retries

Permanent errors (invalid API key, malformed request):
- No retry
- Log and surface to caller

### Fallback Behavior

When all retries and fallback models are exhausted:
- Operations requiring LLM fail with clear error
- No silent degradation that produces incorrect results
- Queue non-urgent requests for later processing if appropriate
- If using agentic architecture (40-agentic-architecture.md), the agent task is marked `failed` with partial results preserved

### Rate Limiting

Implement client-side rate limiting:
- Track requests per minute
- Queue requests when approaching limits
- Spread requests over time window

### Circuit Breaker

Prevent cascade failures when provider is experiencing issues.

**States:**
```
CLOSED ──(failures exceed threshold)──> OPEN
   ^                                      |
   |                                      |
   └──(test succeeds)── HALF_OPEN <──(timeout)──┘
```

**Configuration:**

| Parameter | Value |
|-----------|-------|
| Failure threshold | 5 |
| Failure window | 60 seconds |
| Open duration | 30 seconds |
| Half-open max requests | 1 |

---

## Testing

### Prompt Testing

All prompts have evaluation sets:
- Representative inputs
- Expected output characteristics
- Automated scoring (where applicable)

Run evaluation on:
- Prompt changes
- Model version changes
- Regular intervals (catch model behavior drift)

### Mock Mode

Development and testing can use mock LLM responses:
- Predefined responses for known inputs
- Configurable via environment variable
- Never enabled in production

### Cost in Testing

Test environments use smallest viable models. Advanced models only used in production for designated complex tasks.

---

## Agentic AI Systems (AI-First Platform Profile Only)

For autonomous AI agents — systems where LLMs reason, plan, use tools, collaborate, and maintain memory — see:

- ****40-agentic-architecture.md**** — Conceptual architecture (framework-agnostic): phases, principles, orchestration patterns, AgentTask primitive, safety model
- ****41-agentic-pydanticai.md**** — Implementation guide (PydanticAI-specific): coordinator, agents, middleware, database schema, testing patterns, configuration

This module (24) provides the LLM provider layer, prompt management, cost tracking, and error handling that the agentic architecture depends on. Adopt all three when building agent systems.

---

## Adoption Checklist

When adopting this module:

- [ ] Select LLM provider(s)
- [ ] Implement LLM provider interface (at least one provider)
- [ ] Set up prompt storage and versioning
- [ ] Implement tool/function calling support in provider layer
- [ ] Implement cost tracking (llm_usage table)
- [ ] Configure LLM pricing table
- [ ] Configure fallback models
- [ ] Configure rate limiting
- [ ] Set up circuit breaker
- [ ] Create evaluation datasets for prompts
- [ ] Implement mock mode for testing
- [ ] Configure cost alerts and limits

### For Agentic Systems

If also adopting **40-agentic-architecture.md**:
- [ ] Ensure provider interface supports tool definitions and tool call responses
- [ ] Ensure model version tracking returns exact model from provider response
- [ ] Ensure cost tracking includes duration_ms and fallback_used fields
- [ ] Add agent prompt directory (`config/prompts/agents/`)
- [ ] Follow the Phase 1 checklist in 41-agentic-pydanticai.md

---

## Related Documentation

- **40-agentic-architecture.md** — Agentic AI conceptual architecture (phases, principles, patterns)
- **41-agentic-pydanticai.md** — Agentic AI implementation using PydanticAI
- [21-event-architecture.md](21-event-architecture.md) — Event bus for async processing
- [10-observability.md](10-observability.md) — Logging and monitoring standards
- [14-background-tasks.md](14-background-tasks.md) — Background task processing
