# BFA Platform Architecture Specification

## Purpose

This document defines the agreed architecture for our autonomous agentic AI platform built in Python using the BFA (Backend for Agents) pattern. It serves as the authoritative reference for implementation. Every architectural decision documented here has been deliberated and ratified — do not deviate without explicit approval.

---

## Core Architectural Principle

**Deterministic code owns the orchestration spine. AI intelligence operates at the decision edges.**

The orchestration layers (Playbook, Mission, Mission Control) are implemented as deterministic Python code. AI is invoked only at specific, bounded points: the planning step within Mission Control, the agent execution step, and the Tier 3 verification step. This separation exists for reliability, debuggability, cost predictability, auditability, and compliance in a regulated banking environment.

---

## Execution Hierarchy

```
Playbook [carries Objective metadata] → Mission → Mission Control → Agent(s)
```

Each layer has a clear responsibility boundary. No layer reaches across another. Data flows down as context and up as structured results.

Every Playbook carries an **Objective** — required metadata declaring the strategic business outcome the workflow is designed to achieve. The Objective is not an execution layer. It provides intent (statement), accountability (owner), classification (category), scheduling priority, and optional regulatory traceability. Missions inherit visibility to the Objective for planning context, but the Objective does not alter execution mechanics.

---

## Layer Definitions

### Playbook

- **What it is**: A declarative workflow definition that orchestrates multiple missions.
- **Implementation**: Pure Python code. No AI. No LLM calls.
- **Responsibilities**:
  - Defines which missions execute, in what order, with what dependencies.
  - Manages inter-mission data flow — outputs from Mission A are passed as inputs to Mission B by the Playbook, not by agents.
  - Enforces success/failure gates between missions.
  - Handles rollback logic when missions fail.
  - Calculates worst-case cost before execution by summing mission budgets.
- **Inter-mission data flow**: The Playbook is solely responsible for passing outputs between missions. Agents within Mission B never directly access Mission A's agents. They receive curated context through their Mission Control instance. This is the anti-corruption layer.
- **Execution modes**: Missions may run sequentially, in parallel, or with dependency graphs (A and B parallel, C depends on both). The Playbook defines this statically.
- **Objective metadata**: Every Playbook carries a required Objective that declares the business outcome the workflow is designed to achieve:
  ```yaml
  objective:
    statement: string           # Required. Human-readable business outcome.
    category: string            # Required. Classification for grouping/filtering.
    owner: string               # Required. Accountable person or role.
    priority: string            # Required. critical | high | normal | low
    regulatory_reference: string | null  # Optional. Links to regulatory framework.
  ```
  The Objective is metadata on the Playbook definition, not an execution concern. It flows into observability (structured log context with `objective_category`, `objective_priority`, `objective_owner`), audit records (`MissionRecord` stores `objective_statement` and `objective_category`), and playbook discovery (filtering by category, priority, or owner). Missions within the Playbook have visibility to the objective statement and category for planning context, but the Objective does not change how missions execute.

### Mission

- **What it is**: A discrete objective with clear entry criteria, exit criteria, and bounded scope.
- **Implementation**: Pure Python code. No AI. No LLM calls.
- **Responsibilities**:
  - Defines the mission brief (objective, constraints, input context).
  - Owns timeout policy, retry budget, and resource ceilings (token limits, cost ceilings).
  - Instantiates and invokes its Mission Control instance.
  - Receives structured mission outcome from Mission Control.
  - Reports status back to the Playbook.

### Mission Control

- **What it is**: The deterministic control layer for a mission. It is code that strategically invokes AI at two bounded points: the planning step and (when required) the Tier 3 verification step.
- **Implementation**: Python code with bounded LLM invocations for planning and verification.
- **Metaphor**: Mission Control is not an astronaut. It does not do the work. It orchestrates, monitors, and makes go/no-go decisions. The agents are the astronauts.
- **Responsibilities**:
  - Receives mission brief and upstream context from the Mission layer.
  - Calls the Planning Agent with the mission brief, agent roster, and upstream outputs.
  - Validates the Planning Agent's output against the TaskPlan schema before acting on it.
  - Dispatches worker agents deterministically according to the validated plan.
  - Enforces parallel/sequential execution per the plan's dependency graph.
  - Enforces per-agent timeouts, retry budgets, and cost ceilings.
  - Executes the three-tier verification pipeline for each completed task.
  - Handles retry-with-feedback when verification fails.
  - Collects and aggregates agent results including verification outcomes.
  - Applies quality gates and returns structured mission outcome to the Mission layer.

#### Mission Control Execution Flow

```
Mission Control receives mission brief
    │
    ▼
Builds planning prompt:
  - Mission objective and constraints
  - Agent roster (from static config)
  - Upstream mission outputs (if any)
  - Output format specification (JSON within XML tags)
    │
    ▼
Calls Planning Agent (Opus 4.6, extended thinking):
  - budget_tokens: scaled to mission complexity tier
  - Returns: thinking trace + task plan JSON (includes verification spec per task)
    │
    ▼
Validates task plan:
  - Parse JSON from response
  - Validate against TaskPlan schema
  - Verify all referenced agents exist in roster
  - Verify dependency graph is acyclic (DAG validation)
  - Verify dependency consistency (from_upstream sources appear in dependencies)
  - Verify input compatibility (source_fields exist in source agent output contracts)
  - Verify total estimated cost within mission budget (including verification costs)
  - Verify timeout overrides within allowed maximums
  - Verify critical path tasks exist in task list
  - Verify all deterministic checks reference registered check functions
  - Verify Tier 3 completeness (criteria, evaluator, threshold all present when required)
  - Verify no self-evaluation (no task specifies itself as evaluator)
  - If invalid: retry (max 2 attempts) then fail mission
    │
    ▼
Executes validated plan deterministically:
  - Topologically sorts task DAG
  - Independent tasks run in parallel (asyncio.gather)
  - Sequential dependencies enforced by code
  - Per-agent timeout and cost ceiling enforced
  - For each completed task, runs verification pipeline (see below)
  - Retry-with-feedback on verification failure (within retry budget)
  - Partial failure handling with minimum success thresholds
    │
    ▼
Aggregates results and returns structured mission outcome
```

#### Per-Task Verification Pipeline

After each agent returns output, Mission Control executes verification in sequence. Each tier is cheaper and faster than the next. Execution stops at the first failure.

```
Agent returns output
    │
    ▼
TIER 1: Structural Verification (code, zero tokens, milliseconds)
  - Validate output conforms to agent's interface contract
  - All required fields present with correct types
  - Output is parseable and within size limits
  ├── FAIL → retry agent (within budget) or fail task
  └── PASS ▼
        │
TIER 2: Deterministic Functional Verification (code, zero tokens)
  - Run each deterministic check specified in the task's verification config
  - Examples: terraform validate, run test suite, schema compliance, coverage checks
  - Each check returns pass/fail with details
  ├── FAIL → retry agent with failure details appended to instructions, or fail task
  └── PASS ▼
        │
TIER 3: AI-Based Quality Evaluation (only if specified in task plan)
  - Dispatch Verification Agent (Opus 4.6) with:
    - Original task instructions
    - Evaluation criteria from task plan
    - Agent's actual output
    - Upstream context where relevant
  - Verification Agent returns structured evaluation with per-criterion scores
  - Mission Control makes deterministic pass/fail decision based on scores
  ├── FAIL → retry agent with evaluation feedback, or fail task
  └── PASS ▼
        │
Task marked as successful
```

### Agents

- **What they are**: Vertical specialists. Each has a specific model, specific tools, and a specific system prompt. They receive typed inputs, produce typed outputs, and have no awareness of the broader mission or other agents.
- **Implementation**: LLM calls with tool access, wrapped in typed interfaces.
- **Responsibilities**:
  - Execute a single, well-defined task as instructed by Mission Control.
  - Use only the tools assigned in their agent definition.
  - Return structured output conforming to their interface contract.
  - Have no knowledge of the Playbook, Mission, other agents, or the broader execution context beyond what is passed to them.

---

## Planning Agent Specification

The Planning Agent is a horizontal agent invoked by Mission Control to perform dynamic task decomposition. It is the only point in the system where AI reasoning influences orchestration decisions.

- **Model**: Claude Opus 4.6 with extended thinking enabled.
- **Invocation**: Called by Mission Control (code), not by other agents.
- **Input**: Mission brief, agent roster (including Verification Agent), upstream context, output format spec.
- **Output**: Structured TaskPlan (JSON) defining which agents to invoke, their instructions, dependencies, acceptance criteria, and verification requirements per task.
- **Extended thinking budget**: Scaled per mission complexity tier. Not uncapped.
  - Simple missions (3-5 agents, clear constraints): 5,000-10,000 thinking tokens.
  - Complex missions (conditional branching, 10+ agents): 20,000-30,000 thinking tokens.
  - Budget is set in coordinator config per mission complexity tier, not as a global default.
- **Structured output constraint**: Extended thinking mode does not support `response_format` JSON schema enforcement. The Planning Agent is prompted to return JSON within a specific XML tag. Mission Control extracts, parses, and validates this output in code. Reject and retry on malformed output.
- **Thinking trace**: The `thinking` block from extended thinking is captured and stored as part of the mission audit trail. This provides a complete chain of reasoning for every planning decision. Wire into observability (Langfuse) from day one.
- **System prompt**: Treated as a security-critical, version-controlled artefact. Changes require review and approval. A subtle prompt change can alter how the planner allocates agents and tools across the entire platform.
- **Shared capability**: Single Planning Agent definition (same system prompt, same model) used by all Mission Control instances. Each invocation receives different context (mission brief, roster, upstream outputs). The Planning Agent does not need awareness of other teams or missions.
- **Verification planning responsibility**: The Planning Agent specifies verification requirements per task. It must be prompted to only request Tier 3 AI evaluation when the task output genuinely requires judgment (code generation, analysis, recommendations). Pure data retrieval or transformation tasks should survive on Tier 1 and Tier 2 alone. This is explicitly stated in the Planning Agent's system prompt to control cost.

---

## Verification Agent Specification

The Verification Agent is a dedicated agent in the roster whose sole job is to evaluate other agents' work during Tier 3 verification.

- **Model**: Claude Opus 4.6 with extended thinking enabled.
- **Invocation**: Called by Mission Control (code) as part of the verification pipeline, never by other agents.
- **Input**: Original task instructions, evaluation criteria (from TaskPlan), the agent's actual output, and upstream context where relevant.
- **Output**: Structured evaluation with per-criterion scores, evidence, issues, and recommendations.
- **Isolation rule**: The Verification Agent must never evaluate its own output or the Planning Agent's output. No agent is judge and jury of its own work. This is architecturally enforced — the Verification Agent and worker agents are separate roster entries with separate invocations.
- **Cost awareness**: Every Tier 3 evaluation is an Opus call. For a mission with 5 tasks all requiring Tier 3, this adds 5 Opus invocations to mission cost. The Planning Agent is prompted to use Tier 3 sparingly and only when judgment is genuinely required.
- **Thinking trace**: Stored as part of the verification audit trail. Between the agent's output, the verification evaluation, and the thinking trace, there is a complete audit package for any task.

### Verification Agent Output Contract

```json
{
  "overall_score": 0.92,
  "pass": true,
  "criteria_results": [
    {
      "criterion": "Code addresses all identified policy gaps from the analysis",
      "score": 0.95,
      "pass": true,
      "evidence": "All 7 gaps from the upstream analysis are addressed in modules 1-7...",
      "issues": []
    },
    {
      "criterion": "No overly permissive policies introduced as remediation",
      "score": 0.80,
      "pass": false,
      "evidence": "Module iam_remediation_03 grants broader access than required...",
      "issues": ["admin_role assignment is broader than necessary for the stated objective"]
    }
  ],
  "blocking_issues": [],
  "recommendations": [
    "Consider scoping admin_role to specific resource groups rather than subscription-level"
  ]
}
```

**Mission Control decision logic**: If `overall_score >= min_evaluation_score` (from TaskPlan) AND `blocking_issues` is empty, the task passes. Otherwise, Mission Control retries the worker agent with the evaluation feedback appended to its instructions (the Reflection pattern), or fails the task if retry budget is exhausted.

---

## Agent Roster Design

The agent roster is the contract between Mission Control and the Planning Agent. It defines what the Planning Agent has to work with when decomposing a mission.

### Roster Strategy

- **Initial approach**: Static roster per Mission Control type. Each Mission Control instance is configured with a fixed agent roster. The Planning Agent picks from this fixed menu.
- **Future migration path**: Build a central agent registry as the single source of truth. Initially, Mission Control reads from config files that mirror the registry. Migrate to registry-based lookup when needed.
- **Explicitly excluded**: Dynamic roster with agent discovery by the Planning Agent. No AI control over team composition in a regulated environment.
- **Standard roster agents**: Every roster includes the Planning Agent and Verification Agent by default, plus the mission-specific worker agents.

### Agent Definition Schema

Every agent in the roster must define:

```yaml
agent:
  name: "code_generator"                          # Unique identifier
  description: "Generates Python code from specs"  # Written for LLM comprehension
  version: "1.0.0"                                 # Semantic versioning
  model:
    name: "claude-sonnet-4"                        # PINNED. Non-overridable.
    temperature: 0.0                               # PINNED. Non-overridable.
    max_tokens: 8192                               # PINNED. Non-overridable.
  tools:                                           # Available tool set
    - code_execution
    - file_system
    - package_manager
  interface:
    input:                                         # Typed input contract
      spec: string
      context: string
      constraints: object
    output:                                        # Typed output contract
      code: string
      tests: string
      confidence: float
  constraints:
    timeout_seconds: 120                           # Hard timeout
    cost_ceiling_usd: 0.15                         # Per-invocation cost limit
    parallelism: safe                              # Can run concurrently
    retry_budget: 2                                # Max retries on failure
```

### Model Pinning Policy

- **Models are pinned to agents as immutable, non-overridable properties.** The model is a required field in the agent definition that cannot be overridden at runtime. No parameter allows passing `model="opus"` to an agent configured for Sonnet.
- **Model upgrades are agent version bumps.** To upgrade a model: create `code_generator_v2` with the new model, run the full test suite, validate outputs match or exceed v1, then update the roster config. The old version remains available for rollback.
- **Rationale**: Pinning means tests are meaningful. Validation against Sonnet holds in production because it is the same model, same temperature, same parameters. Dynamic model selection makes every test probabilistic and is indefensible in a regulated environment. It also makes cost modelling predictable — each agent has a known ceiling, and Mission Control can calculate worst-case mission cost before execution.

---

## TaskPlan Schema

The TaskPlan is a directed acyclic graph (DAG) expressed as JSON. It is the handoff point between AI reasoning (Planning Agent) and deterministic execution (Mission Control). Each task is a node. Each dependency is a directed edge. The Planning Agent produces this structure. Mission Control validates and executes it.

### Complete TaskPlan Schema

```json
{
  "task_plan": {
    "version": "1.0.0",
    "mission_id": "string — echoed from input for traceability",
    "summary": "string — human-readable description of the plan for audit trail",
    "estimated_cost_usd": 0.00,
    "estimated_duration_seconds": 0,

    "tasks": [
      {
        "task_id": "analyse_config",
        "agent": "config_scanner",
        "agent_version": "1.0.0",
        "description": "Scan current IAM configuration across all environments",

        "instructions": "string — mission-specific prompt crafted by Planning Agent for this task",

        "inputs": {
          "static": {
            "environments": ["prod", "staging", "dev"],
            "scope": "iam_policies"
          },
          "from_upstream": {}
        },

        "dependencies": [],

        "verification": {
          "tier_1": {
            "schema_validation": true,
            "required_output_fields": ["config_data", "scan_metadata", "confidence"]
          },
          "tier_2": {
            "deterministic_checks": [
              {
                "check": "validate_environment_coverage",
                "params": {
                  "expected_environments": ["prod", "staging", "dev"]
                }
              }
            ]
          },
          "tier_3": {
            "requires_ai_evaluation": false
          }
        },

        "constraints": {
          "timeout_override_seconds": null,
          "priority": "normal"
        }
      },

      {
        "task_id": "analyse_policies",
        "agent": "policy_analyser",
        "agent_version": "1.0.0",
        "description": "Analyse policy documents for compliance gaps against Basel III",

        "instructions": "Review all IAM policies against the Basel III control framework. Identify gaps, rate each by risk severity, and provide evidence references for every finding...",

        "inputs": {
          "static": {
            "framework": "basel_iii",
            "jurisdiction": "multi"
          },
          "from_upstream": {}
        },

        "dependencies": [],

        "verification": {
          "tier_1": {
            "schema_validation": true,
            "required_output_fields": ["findings", "risk_ratings", "evidence_references", "confidence"]
          },
          "tier_2": {
            "deterministic_checks": [
              {
                "check": "validate_risk_rating_scale",
                "params": {
                  "valid_ratings": ["critical", "high", "medium", "low"],
                  "field": "risk_ratings"
                }
              },
              {
                "check": "validate_evidence_references_exist",
                "params": {
                  "findings_field": "findings",
                  "evidence_field": "evidence_references"
                }
              }
            ]
          },
          "tier_3": {
            "requires_ai_evaluation": true,
            "evaluation_criteria": [
              "Analysis covers all major Basel III IAM control domains",
              "Risk ratings are proportionate to the identified gaps",
              "No false positives — each finding references a genuine policy deficiency",
              "Findings are specific and actionable, not generic observations"
            ],
            "evaluator_agent": "verification_agent",
            "min_evaluation_score": 0.85
          }
        },

        "constraints": {
          "timeout_override_seconds": null,
          "priority": "normal"
        }
      },

      {
        "task_id": "generate_remediation",
        "agent": "code_generator",
        "agent_version": "1.0.0",
        "description": "Generate Terraform remediation modules based on config scan and policy analysis",

        "instructions": "Generate Terraform modules to remediate the identified IAM policy gaps. Each module must be environment-parameterised and follow Azure provider best practices...",

        "inputs": {
          "static": {
            "output_format": "terraform",
            "target_provider": "azure"
          },
          "from_upstream": {
            "current_config": {
              "source_task": "analyse_config",
              "source_field": "config_data"
            },
            "policy_findings": {
              "source_task": "analyse_policies",
              "source_field": "findings"
            },
            "risk_ratings": {
              "source_task": "analyse_policies",
              "source_field": "risk_ratings"
            }
          }
        },

        "dependencies": ["analyse_config", "analyse_policies"],

        "verification": {
          "tier_1": {
            "schema_validation": true,
            "required_output_fields": ["code", "tests", "module_manifest", "confidence"]
          },
          "tier_2": {
            "deterministic_checks": [
              {
                "check": "terraform_validate",
                "params": {"strict": true}
              },
              {
                "check": "terraform_plan_dry_run",
                "params": {"expect_no_errors": true}
              },
              {
                "check": "run_generated_tests",
                "params": {"min_pass_rate": 1.0}
              },
              {
                "check": "static_analysis",
                "params": {"tool": "tfsec", "max_critical": 0}
              }
            ]
          },
          "tier_3": {
            "requires_ai_evaluation": true,
            "evaluation_criteria": [
              "Code addresses all identified policy gaps from the upstream analysis",
              "Terraform modules follow Azure best practices for IAM",
              "No overly permissive policies introduced as remediation",
              "Code is modular and environment-parameterised as specified",
              "Each remediation maps to a specific finding with traceability"
            ],
            "evaluator_agent": "verification_agent",
            "min_evaluation_score": 0.85
          }
        },

        "constraints": {
          "timeout_override_seconds": 180,
          "priority": "high"
        }
      }
    ],

    "execution_hints": {
      "min_success_threshold": 0.66,
      "critical_path": ["analyse_config", "generate_remediation"]
    }
  }
}
```

### TaskPlan Schema Field Reference

#### Top-Level Fields

| Field | Type | Description |
|---|---|---|
| `version` | string | Schema version. Semantic versioning. |
| `mission_id` | string | Echoed from Mission input for traceability. |
| `summary` | string | Human-readable plan description for audit trail. |
| `estimated_cost_usd` | float | Planning Agent's estimate of total execution cost including verification. Mission Control validates against mission budget. |
| `estimated_duration_seconds` | int | Planning Agent's estimate of total wall-clock time accounting for parallelism. |

#### Task Fields

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Unique identifier within the plan. Used in dependency references. |
| `agent` | string | Agent name from roster. Mission Control validates existence. |
| `agent_version` | string | Agent version from roster. Mission Control validates match. |
| `description` | string | Human-readable task description for audit trail. |
| `instructions` | string | Mission-specific prompt crafted by Planning Agent. This is what the agent receives as its task. |
| `inputs.static` | object | Fixed input values defined by the Planning Agent. |
| `inputs.from_upstream` | object | References to outputs from other tasks. Keys are input field names the agent expects per its roster interface. Values specify `source_task` and `source_field`. Mission Control resolves at execution time by substituting actual outputs from completed tasks. |
| `dependencies` | array[string] | Task IDs that must complete successfully before this task starts. Must include all tasks referenced in `from_upstream`. May include additional tasks for ordering without data flow. |
| `constraints.timeout_override_seconds` | int or null | Optional timeout override. Mission Control validates against roster maximum and mission budget. Null means use roster default. |
| `constraints.priority` | string | `"normal"`, `"high"`, or `"critical"`. Informs execution ordering when resources are constrained. |

#### Verification Fields

| Field | Type | Description |
|---|---|---|
| `tier_1.schema_validation` | bool | Whether to validate output against agent interface contract. Should always be true. |
| `tier_1.required_output_fields` | array[string] | Fields that must be present in output. Validated against agent roster output contract. |
| `tier_2.deterministic_checks` | array[object] | Named check functions to execute. Each has `check` (registered function name) and `params` (check-specific config). |
| `tier_3.requires_ai_evaluation` | bool | Whether this task requires Verification Agent evaluation. False for data retrieval/transformation. True for generation, analysis, recommendations requiring judgment. |
| `tier_3.evaluation_criteria` | array[string] | Criteria the Verification Agent evaluates against. Written by Planning Agent based on mission objectives. Only present when `requires_ai_evaluation` is true. |
| `tier_3.evaluator_agent` | string | Agent name for verification. Always `"verification_agent"` in v1. Must exist in roster. |
| `tier_3.min_evaluation_score` | float | Pass/fail threshold. Mission Control compares Verification Agent's `overall_score` against this value. |

#### Execution Hints Fields

| Field | Type | Description |
|---|---|---|
| `min_success_threshold` | float | Fraction of tasks that must succeed for partial success rather than failure. |
| `critical_path` | array[string] | Task IDs that must succeed regardless of threshold. Any critical path failure means mission failure. |

---

## TaskPlan Validation Rules

Mission Control executes all validation rules before beginning task execution. Any failure rejects the plan.

1. **Schema validation** — all required fields present with correct types at every level.
2. **Agent validation** — every `agent` + `agent_version` combination exists in the roster.
3. **DAG validation** — topological sort succeeds. Cycles are rejected.
4. **Dependency consistency** — every `source_task` in any `from_upstream` block also appears in that task's `dependencies` array.
5. **Input compatibility** — every `source_field` referenced in `from_upstream` exists in the source agent's output contract as defined in the roster.
6. **Check registry validation** — every `check` name in `tier_2.deterministic_checks` references a function registered in Mission Control's check registry.
7. **Budget validation** — `estimated_cost_usd` is within the mission budget ceiling (including verification costs).
8. **Timeout validation** — any `timeout_override_seconds` is within the allowed maximum defined in roster constraints.
9. **Critical path validation** — all task IDs in `execution_hints.critical_path` exist in the task list.
10. **Tier 3 completeness** — if `requires_ai_evaluation` is true, then `evaluation_criteria`, `evaluator_agent`, and `min_evaluation_score` must all be present. The `evaluator_agent` must exist in the roster.
11. **Self-evaluation prevention** — no task specifies itself as the `evaluator_agent`.

If validation fails: log the specific failure with the invalid field path, retry the Planning Agent (max 2 attempts), then fail the mission with a diagnostic report.

---

## Mission Control Structured Output Contract

Every Mission Control instance returns the same typed structure to the Mission layer:

```yaml
mission_outcome:
  mission_id: string
  status: "success" | "partial" | "failed"
  artifacts:                                       # References, not inline content
    - type: string
      reference: string
      size_bytes: int
  task_results:
    - task_id: string
      agent_name: string
      status: "success" | "failed" | "timeout"
      confidence: float
      output_reference: string
      token_usage:
        input: int
        output: int
        thinking: int
      cost_usd: float
      duration_seconds: float
      verification_outcome:
        tier_1:
          status: "pass" | "fail" | "skipped"
          details: string
        tier_2:
          status: "pass" | "fail" | "skipped"
          checks_run: int
          checks_passed: int
          failed_checks:
            - check: string
              reason: string
        tier_3:
          status: "pass" | "fail" | "skipped"
          overall_score: float
          criteria_results_reference: string       # Link to full evaluation
          evaluator_thinking_trace_reference: string
          cost_usd: float
      retry_count: int
      retry_history:                               # Only populated if retries occurred
        - attempt: int
          failure_tier: int
          failure_reason: string
          feedback_provided: string
  total_cost_usd: float                            # Including verification costs
  total_duration_seconds: float
  total_tokens:
    input: int
    output: int
    thinking: int
  planning_trace_reference: string                 # Link to stored Planning Agent thinking trace
  task_plan_reference: string                      # Link to stored validated TaskPlan
  flags:
    - human_review_required: bool
      reason: string
```

---

## Multi-Team Execution Pattern

Teams map to Mission Control instances with dedicated agent pools. The Playbook orchestrates teams via missions. Every roster includes the Planning Agent and Verification Agent alongside mission-specific worker agents.

```
Playbook: "Deploy IAM Policy Update"
│
├── Mission 1: "Analyse Current State"
│   └── Mission Control A
│       ├── Planning Agent (Opus 4.6) → task plan with verification spec
│       ├── Config Scanner Agent (Sonnet + API tools)
│       ├── Policy Analyser Agent (Sonnet + doc tools)
│       └── Verification Agent (Opus 4.6) → evaluates analysis quality
│
├── Mission 2: "Generate Changes" [depends on Mission 1]
│   └── Mission Control B
│       ├── Planning Agent (Opus 4.6) → task plan with verification spec
│       ├── Code Gen Agent (Sonnet + coding tools)
│       ├── Test Gen Agent (Sonnet + test framework)
│       └── Verification Agent (Opus 4.6) → evaluates code quality
│
└── Mission 3: "Review & Approve" [depends on Mission 2]
    └── Mission Control C
        ├── Planning Agent (Opus 4.6) → task plan with verification spec
        ├── Security Review Agent (Opus + policy KB)
        ├── Compliance Check Agent (Sonnet + reg tools)
        └── Verification Agent (Opus 4.6) → evaluates review thoroughness
```

### Inter-Team Communication Rules

- Teams do **not** communicate directly with each other.
- All inter-team data flow is managed by the Playbook layer.
- The Playbook passes Mission 1 outputs to Mission 2's Mission Control as input context.
- Agents within a mission receive only the context their Mission Control provides.
- Agents produce artifacts that persist independently (stored externally, referenced by lightweight handles) — not passed inline through the agent chain. This avoids the "game of telephone" problem and reduces token overhead.

---

## Error Recovery and Resilience

All resilience logic lives in the deterministic code layers, not in agents.

- **Agent-level**: Exponential backoff with jitter for transient LLM failures. Per-agent retry budget defined in roster. Hard timeout enforced by Mission Control.
- **Verification-level**: When Tier 2 or Tier 3 fails, Mission Control retries the worker agent with specific failure details or evaluation feedback appended to its instructions (the Reflection pattern). This dramatically improves output quality on retry. Retry budget in the roster must account for verification-triggered retries — each retry-with-feedback doubles cost and latency for that task.
- **Mission Control-level**: Planning Agent retry (max 2) on malformed output. Minimum success thresholds for partial completion (e.g., 2 of 5 agents must succeed). Circuit breaker if model endpoint degrades.
- **Mission-level**: Retry budget and timeout defined by Mission config. Fail-fast or degrade-gracefully as configured.
- **Playbook-level**: Rollback logic for dependent missions. If Mission 2 fails, Playbook decides whether to retry, skip, or abort the entire workflow.

---

## Observability Requirements

- **Langfuse** as the primary observability platform (open-source, Apache 2.0).
- `@observe()` decorator on all agent invocations for auto-linked trace trees.
- Extended thinking traces stored as metadata on Planning Agent and Verification Agent spans.
- Verification outcomes logged per task per tier with full detail.
- Consistent metaphor in logging: Mission Control "launches" agents, agents "report telemetry," missions have "go/no-go" gates, verification is "inspection."
- Key metrics per execution:
  - Per-agent success rate (pre-verification and post-verification)
  - Per-tier pass/fail rates
  - Verification cost as percentage of total mission cost
  - Retry-with-feedback success rate (quality improvement from Reflection pattern)
  - Token usage by model (input, output, thinking)
  - Tool execution latency at P95
  - Cost per agent invocation
  - Cost per verification invocation
  - Cost per mission (broken down: planning + execution + verification)
  - Cost per playbook execution
  - Planning Agent thinking token usage vs budget

---

## Security Considerations

- Planning Agent system prompts are **security-critical, version-controlled artefacts**. Changes require review and approval.
- Verification Agent system prompts are equally security-critical — they define what "good" looks like for the platform.
- Agent tool access is defined in the roster and enforced by Mission Control. Agents cannot acquire tools at runtime.
- The BFA layer beneath agents encapsulates domain APIs, enforces access policies, handles caching and logging, and exposes stable operations. Agents interact with backends through BFA facades, never directly.
- All agent outputs are validated by deterministic code (Tier 1 and Tier 2) before being acted upon or passed to downstream missions. Tier 3 AI evaluation provides additional assurance for high-judgment tasks.
- Model parameters (model name, temperature, max tokens) are immutable properties of agent definitions. No runtime override path exists.
- The Verification Agent never evaluates its own output or the Planning Agent's output. This isolation is architecturally enforced.

---

## Implementation Sequence

1. Define the agent definition schema and roster format.
2. Define the TaskPlan JSON schema with verification tiers.
3. Build the deterministic check registry with initial check functions.
4. Build Mission Control as a Python class with the full execution flow including the verification pipeline.
5. Implement the Planning Agent with Opus 4.6 extended thinking, including structured output parsing and validation.
6. Implement the Verification Agent with structured evaluation output.
7. Build the Mission layer with lifecycle management (start, run, succeed/fail, report).
8. Build the Playbook layer with mission dependency graph execution.
9. Integrate Langfuse observability across all layers including verification spans.
10. Build the BFA tool layer beneath agents.
11. Write integration tests at every boundary: Playbook→Mission, Mission→Mission Control, Mission Control→Planning Agent, Mission Control→Worker Agent, Mission Control→Verification Agent.

---

## Decisions Log

| Decision | Choice | Rationale |
|---|---|---|
| Coordinator pattern | Code, not agent (Option A) | Reliability, debuggability, auditability in regulated environment |
| Planning agent position | Invoked BY Mission Control, not above it | Keeps non-determinism bounded; deterministic code handles inter-mission coordination |
| Planning agent model | Claude Opus 4.6, extended thinking | Best reasoning capability for task decomposition |
| Model assignment | Pinned to agents, non-overridable | Predictable testing, cost control, regulatory defensibility |
| Agent roster strategy | Static per Mission Control, with registry planned | Simplicity first; registry for future scale |
| Inter-team communication | Via Playbook only, never direct | Anti-corruption layer; agents don't need cross-team awareness |
| Coordinator naming | "Mission Control" | Communicates the right mental model to all stakeholders |
| Error handling ownership | Deterministic code layers only | Agents don't make resilience decisions |
| Observability | Langfuse with thinking trace capture | Open-source, async-safe, captures extended thinking for audit |
| TaskPlan structure | DAG expressed as JSON | Supports parallelism and sequential dependencies in a single structure |
| Task input mapping | Explicit field-level from_upstream references | Type-safe wiring resolved by Mission Control at execution time |
| Conditional branching | Excluded from v1 | Mission Control handles failure via code. Revisit in v2 if needed |
| Deterministic checks | Closed set of registered function names | Prevents Planning Agent from referencing hallucinated checks |
| Verification model | Three-tier: structural → deterministic → AI evaluation | Cheapest/fastest checks first. AI only when judgment required |
| Verification agent model | Claude Opus 4.6, extended thinking | Quality evaluation requires best reasoning capability |
| Verification agent isolation | Cannot evaluate own output or Planning Agent output | No agent is judge and jury of its own work |
| Tier 3 usage policy | Planning Agent decides per task, prompted for restraint | Controls cost; pure data tasks survive on Tier 1 and 2 |
| Retry with feedback | Evaluation details appended to agent instructions on retry | Reflection pattern improves quality; retry budget accounts for cost |
| Objective placement | Metadata on Playbook definition, not an execution layer | No execution logic needed. Category/priority enable filtering and reporting. Owner enables accountability. Regulatory reference supports compliance traceability. If multiple Playbooks per Objective needed in future, Objective promotes to first-class entity (v2). |

---

## TaskPlan Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Graph structure | DAG (Directed Acyclic Graph) | Expresses parallelism and sequential dependencies naturally |
| Input mapping | Explicit field-level via from_upstream | Type-safe wiring; Mission Control resolves and catches mismatches before dispatch |
| Dependencies array | Intentionally redundant with from_upstream | Supports ordering-only dependencies without data flow |
| Conditional branching | Excluded from v1 | Adds complexity; Mission Control handles failure via retry and thresholds |
| Loops | Excluded from v1 | Retry logic belongs to Mission Control code, not the plan |
| Per-task retry spec | Excluded from plan | Retry budgets defined in roster, enforced by Mission Control |
| Per-task model selection | Excluded permanently | Models pinned in roster; Planning Agent selects agents not models |
| Verification per task | Planning Agent specifies, Mission Control validates and executes | Separates judgment (which tasks need what verification) from execution (running the checks) |

---

## Future Considerations

### Objective as First-Class Entity

Currently, the Objective is required metadata on the Playbook definition. If the platform later requires multiple Playbooks serving a single Objective (e.g., running the same compliance objective across different jurisdictions with different Playbooks), then the Objective may be promoted to a first-class entity that groups and orchestrates Playbooks. This is explicitly a v2 concern. The current metadata-only approach is sufficient for all v1 use cases and avoids architectural overhead.

### Objective-Driven Playbook Selection

The Objective's `category` and `priority` fields open future possibilities for objective-driven playbook recommendation: given a business objective description, the system could suggest matching playbooks. Not implemented in v1 — playbook selection remains explicit (on-demand trigger or pattern matching).
