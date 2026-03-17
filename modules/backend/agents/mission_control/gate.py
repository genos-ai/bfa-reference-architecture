"""
Step-Through Gate — human/AI-in-the-loop review mechanism.

Pauses execution at key decision points in the dispatch loop, presents
context, and waits for a reviewer (human or AI) to approve, reject,
modify, skip, or retry before proceeding.

Modes (configured in config/settings/gate.yaml):
    off          — NoOpGate (default). Zero overhead.
    interactive  — CliGateReviewer via Rich prompts.
    ai_assisted  — LLM recommends, human decides.
    autonomous   — LLM decides, no human.

CLI override: --gate <mode>  (--step is an alias for --gate interactive)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ── Enums and data models ────────────────────────────────────────────────


class GateAction(str, Enum):
    """Reviewer actions at a gate point."""

    CONTINUE = "continue"   # Proceed to next step
    SKIP = "skip"           # Skip this task/layer, mark SKIPPED
    RETRY = "retry"         # Re-run the task (with optional modified inputs)
    ABORT = "abort"         # Halt the entire mission
    MODIFY = "modify"       # Proceed with modified inputs/instructions


@dataclass
class GateContext:
    """Everything the reviewer needs to make a decision.

    All fields are JSON-serializable so both CLI and AI reviewers
    can consume the same data.
    """

    gate_type: str               # pre_dispatch, pre_layer, post_task,
                                 # verification_failed, post_layer
    mission_id: str
    layer_index: int = 0
    total_layers: int = 0

    # Pre-layer: tasks about to execute
    pending_tasks: list[dict] = field(default_factory=list)

    # Post-task: completed task details
    task_id: str | None = None
    task_result: dict | None = None     # TaskResult as dict
    task_output: dict | None = None     # Raw agent output
    verification: dict | None = None    # VerificationOutcome as dict

    # Aggregates
    completed_tasks: list[dict] = field(default_factory=list)
    total_cost_usd: float = 0.0
    budget_usd: float = 0.0

    # For retry/modify
    current_instructions: str | None = None
    current_inputs: dict | None = None

    # AI reviewer recommendation (populated by ConfigurableGate in ai_assisted mode)
    ai_recommendation: Any = None


@dataclass
class GateDecision:
    """Reviewer's decision at a gate point."""

    action: GateAction
    reason: str | None = None
    modified_inputs: dict | None = None        # For MODIFY action
    modified_instructions: str | None = None   # For RETRY with feedback
    reviewer: str = "human"                    # human, ai:<model>, noop, config:disabled


class GateReviewer(Protocol):
    """Abstract reviewer — human, AI, or composite.

    Implementations:
    - NoOpGate: always continues (off mode)
    - CliGateReviewer: interactive Rich prompts (interactive mode)
    - LlmGateReviewer: thinking LLM reviews (autonomous mode)
    - ConfigurableGate: per-gate-point mode routing (ai_assisted, mixed)
    """

    async def review(self, context: GateContext) -> GateDecision: ...


# ── Concrete implementations ────────────────────────────────────────────


class NoOpGate:
    """Pass-through gate that always continues. Zero overhead."""

    async def review(self, context: GateContext) -> GateDecision:
        return GateDecision(action=GateAction.CONTINUE, reviewer="noop")


class LlmGateReviewer:
    """AI gate reviewer — uses an LLM to analyze gate context and decide.

    Serializes GateContext into a structured prompt, calls the LLM with
    a JSON-output instruction, and parses the response into a GateDecision.

    Uses PydanticAI Agent for structured output, consistent with the rest
    of the codebase.
    """

    def __init__(
        self,
        model: str = "anthropic:claude-haiku-4-5-20251001",
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ):
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._agent = None  # Lazy init to avoid import cost when unused

    def _get_agent(self):
        """Lazily build the PydanticAI agent on first use."""
        if self._agent is not None:
            return self._agent

        from pydantic import BaseModel, Field
        from pydantic_ai import Agent
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        from modules.backend.core.config import get_settings

        class GateReviewOutput(BaseModel):
            """Structured output from the AI gate reviewer."""

            action: str = Field(
                description="One of: continue, skip, retry, abort, modify",
            )
            reason: str = Field(
                default="",
                description="Brief explanation for the decision",
            )
            modified_instructions: str | None = Field(
                default=None,
                description="Feedback for retry (only when action=retry)",
            )

        settings = get_settings()
        bare_name = self.model_name.split(":", 1)[1] if ":" in self.model_name else self.model_name
        provider = AnthropicProvider(api_key=settings.anthropic_api_key)
        model = AnthropicModel(bare_name, provider=provider)

        self._agent = Agent(
            model,
            system_prompt=_GATE_SYSTEM_PROMPT,
            output_type=GateReviewOutput,
        )
        return self._agent

    async def review(self, context: GateContext) -> GateDecision:
        """Analyze gate context and return a structured decision."""
        agent = self._get_agent()
        user_prompt = _build_gate_prompt(context)

        try:
            result = await agent.run(
                user_prompt,
                model_settings={
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                },
            )
            output = result.output
            action = _parse_action(output.action)
            return GateDecision(
                action=action,
                reason=output.reason or None,
                modified_instructions=output.modified_instructions,
                reviewer=f"ai:{self.model_name}",
            )
        except Exception:
            logger.warning(
                "LLM gate review failed, falling back to CONTINUE",
                exc_info=True,
            )
            return GateDecision(
                action=GateAction.CONTINUE,
                reason="LLM review failed — auto-continuing",
                reviewer=f"ai:{self.model_name}:fallback",
            )


class ConfigurableGate:
    """Gate that routes to the appropriate reviewer per gate point.

    Reads GateSchema config and routes each gate_type to the correct
    reviewer based on the effective mode (per-point override or top-level).

    This is the main gate implementation used when any gate mode is active.
    """

    def __init__(
        self,
        config: Any,            # GateSchema from config_schema.py
        console: Any = None,    # Rich Console for CLI modes
        verbose: bool = False,
    ):
        from modules.backend.core.config_schema import GateSchema

        if not isinstance(config, GateSchema):
            raise TypeError(f"Expected GateSchema, got {type(config).__name__}")

        self._config = config
        self._console = console
        self._verbose = verbose

        # Lazily initialized reviewers
        self._llm: LlmGateReviewer | None = None
        self._cli: Any = None  # CliGateReviewer — lazy to avoid Rich import

    def _get_llm(self) -> LlmGateReviewer:
        """Get or create the LLM reviewer."""
        if self._llm is None:
            ai = self._config.ai
            self._llm = LlmGateReviewer(
                model=ai.model,
                temperature=ai.temperature,
                max_tokens=ai.max_tokens,
            )
        return self._llm

    def _get_cli(self):
        """Get or create the CLI reviewer."""
        if self._cli is None:
            from modules.backend.cli.gate import CliGateReviewer
            self._cli = CliGateReviewer(
                console=self._console,
                verbose=self._verbose,
            )
        return self._cli

    def _effective_mode(self, gate_type: str) -> str:
        """Resolve the effective mode for a gate point.

        Per-point mode overrides top-level; None inherits.
        """
        point_config = getattr(self._config.points, gate_type, None)
        if point_config and point_config.mode is not None:
            return point_config.mode
        return self._config.mode

    def _is_enabled(self, gate_type: str) -> bool:
        """Check if a gate point is enabled."""
        point_config = getattr(self._config.points, gate_type, None)
        if point_config is None:
            return True
        return point_config.enabled

    def _should_auto_continue(self, context: GateContext) -> bool:
        """Check auto-continue rules for autonomous mode.

        Returns True if the gate point can be skipped without calling the LLM.
        """
        rules = self._config.auto_rules

        # Cost check: auto-continue if cost is below threshold
        if context.budget_usd > 0:
            cost_pct = (context.total_cost_usd / context.budget_usd) * 100
            if cost_pct >= rules.cost_threshold_pct:
                return False  # Cost is high — need LLM review

        # Pre-layer: auto-continue if few tasks
        if context.gate_type == "pre_layer":
            if len(context.pending_tasks) <= rules.max_tasks_per_layer:
                return True

        # Post-task: auto-continue if verification passed
        if context.gate_type == "post_task" and rules.skip_post_task_on_pass:
            if context.verification:
                tier1 = context.verification.get("tier_1", {})
                tier2 = context.verification.get("tier_2", {})
                if tier1.get("status") != "fail" and tier2.get("status") != "fail":
                    return True

        # Verification failures always need review
        if context.gate_type == "verification_failed":
            return False

        # Pre-dispatch: always review (it's the plan overview)
        if context.gate_type == "pre_dispatch":
            return False

        # Post-layer: auto-continue (high-cost case already exited above)
        if context.gate_type == "post_layer":
            return True

        return False

    async def review(self, context: GateContext) -> GateDecision:
        """Route to the appropriate reviewer based on config."""
        gate_type = context.gate_type

        # Check if this gate point is disabled
        if not self._is_enabled(gate_type):
            return GateDecision(
                action=GateAction.CONTINUE,
                reviewer="config:disabled",
            )

        effective_mode = self._effective_mode(gate_type)

        if effective_mode == "off":
            return GateDecision(
                action=GateAction.CONTINUE,
                reviewer="config:off",
            )

        if effective_mode == "interactive":
            return await self._get_cli().review(context)

        if effective_mode == "ai_assisted":
            # AI recommends, human decides
            recommendation = await self._get_llm().review(context)
            context.ai_recommendation = recommendation
            return await self._get_cli().review(context)

        if effective_mode == "autonomous":
            # Check auto-continue rules first to save LLM cost
            if self._should_auto_continue(context):
                return GateDecision(
                    action=GateAction.CONTINUE,
                    reason="auto-rule: conditions met",
                    reviewer="config:auto",
                )
            return await self._get_llm().review(context)

        # Unknown mode — safe fallback
        logger.warning("Unknown gate mode '%s', falling back to off", effective_mode)
        return GateDecision(
            action=GateAction.CONTINUE,
            reviewer=f"config:unknown:{effective_mode}",
        )


# ── Factory ──────────────────────────────────────────────────────────────


def create_gate(
    mode_override: str | None = None,
    console: Any = None,
    verbose: bool = False,
) -> GateReviewer | None:
    """Create the appropriate gate reviewer from config + CLI override.

    Args:
        mode_override: CLI --gate flag value. Overrides gate.yaml mode.
        console: Rich Console for CLI modes.
        verbose: Enable verbose CLI output.

    Returns:
        GateReviewer instance, or None if mode is "off".
    """
    from modules.backend.core.config import get_app_config
    from modules.backend.core.config_schema import GateSchema

    config: GateSchema = get_app_config().gate

    # Apply CLI override
    if mode_override is not None:
        config = config.model_copy(update={"mode": mode_override})

    if config.mode == "off":
        return None

    return ConfigurableGate(
        config=config,
        console=console,
        verbose=verbose,
    )


# ── LLM prompt construction ─────────────────────────────────────────────


_GATE_SYSTEM_PROMPT = """\
You are a gate reviewer for a multi-agent mission dispatch system.

Your role is to review execution state at key decision points and decide
whether to continue, skip, retry, abort, or modify the current step.

You will receive structured context about the current gate point including:
- Gate type (pre_dispatch, pre_layer, post_task, verification_failed, post_layer)
- Mission ID and budget information
- Task details, outputs, and verification results
- Cost tracking and layer progress

Decision guidelines:
- CONTINUE: Proceed normally. Use when everything looks healthy.
- SKIP: Skip this task or layer. Use when a task is unnecessary or redundant.
- RETRY: Re-run with feedback. Use when output is close but needs adjustment.
- ABORT: Halt the entire mission. Use for budget overruns, cascading failures,
  or when the mission objective cannot be met.
- MODIFY: Accept output despite issues. Use when verification failed but the
  output is still usable (only at verification_failed gates).

Cost awareness:
- Flag when cumulative cost exceeds 80% of budget.
- Consider cost-per-value: abort if remaining tasks won't justify spend.

Quality awareness:
- At post_task: check that output matches the task description and verification passed.
- At verification_failed: assess severity. Minor schema issues may be acceptable;
  fundamental quality failures should trigger retry or abort.

Respond with your decision as structured JSON.
"""


def _build_gate_prompt(context: GateContext) -> str:
    """Build a user-facing prompt from gate context for the LLM reviewer."""
    parts = [f"## Gate Point: {context.gate_type}\n"]

    parts.append(f"**Mission:** {context.mission_id}")
    parts.append(
        f"**Budget:** ${context.total_cost_usd:.4f} spent "
        f"/ ${context.budget_usd:.2f} total"
    )

    if context.budget_usd > 0:
        pct = (context.total_cost_usd / context.budget_usd) * 100
        parts.append(f"**Budget utilization:** {pct:.1f}%")

    if context.gate_type == "pre_dispatch":
        parts.append(f"\n**Tasks in plan:** {len(context.pending_tasks)}")
        if context.pending_tasks:
            task_summary = json.dumps(
                [
                    {
                        "task_id": t.get("task_id"),
                        "agent": t.get("agent"),
                        "description": (t.get("description") or "")[:100],
                    }
                    for t in context.pending_tasks
                ],
                indent=2,
            )
            parts.append(f"\n```json\n{task_summary}\n```")

    elif context.gate_type == "pre_layer":
        parts.append(
            f"\n**Layer:** {context.layer_index + 1}/{context.total_layers}"
        )
        parts.append(f"**Tasks in layer:** {len(context.pending_tasks)}")
        if context.pending_tasks:
            task_summary = json.dumps(
                [
                    {
                        "task_id": t.get("task_id"),
                        "agent": t.get("agent"),
                        "instructions": (t.get("instructions") or "")[:80],
                    }
                    for t in context.pending_tasks
                ],
                indent=2,
            )
            parts.append(f"\n```json\n{task_summary}\n```")

    elif context.gate_type == "post_task":
        parts.append(f"\n**Task:** {context.task_id}")
        if context.task_output:
            meta = context.task_output.get("_meta", {})
            parts.append(
                f"**Task cost:** ${meta.get('cost_usd', 0):.4f}  |  "
                f"Tokens: {meta.get('input_tokens', 0):,} in / "
                f"{meta.get('output_tokens', 0):,} out"
            )
            # Show output summary (truncated)
            output_preview = {
                k: v for k, v in context.task_output.items()
                if k != "_meta"
            }
            preview_str = json.dumps(output_preview, indent=2, default=str)
            if len(preview_str) > 1000:
                preview_str = preview_str[:1000] + "\n... (truncated)"
            parts.append(f"\n**Output:**\n```json\n{preview_str}\n```")
        if context.verification:
            parts.append(
                f"\n**Verification:**\n```json\n"
                f"{json.dumps(context.verification, indent=2, default=str)}\n```"
            )

    elif context.gate_type == "verification_failed":
        parts.append(f"\n**Task:** {context.task_id}")
        parts.append("**Status:** VERIFICATION FAILED")
        if context.verification:
            parts.append(
                f"\n**Verification details:**\n```json\n"
                f"{json.dumps(context.verification, indent=2, default=str)}\n```"
            )
        parts.append(
            "\nDecide: retry (with feedback), modify (accept despite failure), "
            "skip, or abort."
        )

    elif context.gate_type == "post_layer":
        parts.append(
            f"\n**Layer:** {context.layer_index + 1}/{context.total_layers} complete"
        )
        if context.completed_tasks:
            statuses: dict[str, int] = {}
            for t in context.completed_tasks:
                s = t.get("status", "?")
                statuses[s] = statuses.get(s, 0) + 1
            parts.append(f"**Results:** {statuses}")

    parts.append("\nWhat is your decision?")
    return "\n".join(parts)


def _parse_action(action_str: str) -> GateAction:
    """Parse action string to GateAction enum, with fallback."""
    try:
        return GateAction(action_str.lower().strip())
    except ValueError:
        logger.warning("Unknown gate action '%s', defaulting to CONTINUE", action_str)
        return GateAction.CONTINUE
