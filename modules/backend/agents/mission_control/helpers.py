"""Mission Control shared helpers — agent building, routing, event plumbing.

Private infrastructure extracted from mission_control.py to keep files
under the 500-line target.  Everything here is an implementation detail;
the public API lives in mission_control.py.
"""

from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from modules.backend.schemas.session import SessionResponse

from pydantic_ai import UsageLimits
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from modules.backend.agents.config_schema import AgentConfigSchema, AgentModelSchema
from modules.backend.agents.deps.base import (
    BaseAgentDeps,
    FileScope,
    HealthAgentDeps,
    QaAgentDeps,
)
from modules.backend.agents.mission_control.middleware import _load_mission_control_config
from modules.backend.agents.mission_control.models import (
    EventBusProtocol,
    ExecuteAgentFn,
    MissionControlRequest,
)
from modules.backend.core.protocols import SessionServiceProtocol
from modules.backend.agents.mission_control.registry import get_registry
from modules.backend.agents.mission_control.roster import Roster
from modules.backend.agents.mission_control.router import RuleBasedRouter
from modules.backend.core.config import find_project_root, get_app_config, get_settings
from modules.backend.agents.mission_control.cost import compute_cost_usd
from modules.backend.core.exceptions import ApplicationError, ValidationError
from modules.backend.core.logging import get_logger
from modules.backend.events.types import SessionEvent
from modules.backend.schemas.session import SessionMessageCreate

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Model / prompt construction
# ---------------------------------------------------------------------------


def _build_model(config_model: str | AgentModelSchema) -> Model:
    """Construct a PydanticAI Model from config string or AgentModelSchema."""
    if isinstance(config_model, AgentModelSchema):
        model_name = config_model.name
    else:
        model_name = config_model

    settings = get_settings()

    if model_name.startswith("anthropic:"):
        bare_name = model_name.split(":", 1)[1]
        provider = AnthropicProvider(api_key=settings.anthropic_api_key)
        return AnthropicModel(bare_name, provider=provider)

    raise ValidationError(f"Unsupported model provider in '{model_name}'. Expected 'anthropic:model_name'.")


def assemble_instructions(category: str, name: str) -> str:
    """Compose layered prompt: organization -> category -> agent.

    Reads markdown files from config/prompts/ and concatenates them.
    Missing layers are silently skipped.
    """
    project_root = find_project_root()
    prompts_dir = project_root / "config" / "prompts"
    layers: list[str] = []

    org_dir = prompts_dir / "organization"
    if org_dir.exists():
        for org_file in sorted(org_dir.glob("*.md")):
            layers.append(org_file.read_text(encoding="utf-8").strip())

    cat_file = prompts_dir / "categories" / f"{category}.md"
    if cat_file.exists():
        layers.append(cat_file.read_text(encoding="utf-8").strip())

    agent_file = prompts_dir / "agents" / category / name / "system.md"
    if agent_file.exists():
        layers.append(agent_file.read_text(encoding="utf-8").strip())

    return "\n\n".join(layers)


def _get_model_name(config_model: str | AgentModelSchema) -> str:
    """Extract model name string from config model."""
    if isinstance(config_model, AgentModelSchema):
        return config_model.name
    return config_model


# ---------------------------------------------------------------------------
# Agent deps / setup
# ---------------------------------------------------------------------------


def build_deps_from_config(agent_config: AgentConfigSchema) -> dict[str, Any]:
    """Build common dep fields from agent YAML config."""
    scope = FileScope(
        read_paths=agent_config.scope.read,
        write_paths=agent_config.scope.write,
    )
    return {
        "project_root": find_project_root(),
        "scope": scope,
        "config": agent_config,
    }


def _build_agent_deps(
    agent_name: str,
    agent_config: AgentConfigSchema,
    session_id: str | None = None,
) -> BaseAgentDeps:
    """Build the appropriate deps dataclass for a given agent."""
    common = build_deps_from_config(agent_config)
    common["session_id"] = session_id
    category = agent_name.split(".")[0]

    if category == "system" and "health" in agent_name:
        return HealthAgentDeps(**common, app_config=get_app_config())
    if category == "code":
        return QaAgentDeps(**common)

    return BaseAgentDeps(**common)


def _get_usage_limits(agent_name: str | None = None) -> UsageLimits:
    """Build UsageLimits, preferring per-agent overrides from agent.yaml.

    Resolution order:
        1. Per-agent max_tokens / max_requests from agent.yaml (if set)
        2. System defaults from mission_control.yaml limits
    """
    mc_config = _load_mission_control_config()
    system_tokens = mc_config.limits.max_tokens_per_task
    system_requests = mc_config.limits.max_requests_per_task

    if agent_name:
        try:
            agent_config = get_registry().get(agent_name)
            return UsageLimits(
                request_limit=agent_config.max_requests or system_requests,
                total_tokens_limit=agent_config.max_tokens or system_tokens,
            )
        except KeyError:
            pass

    return UsageLimits(
        request_limit=system_requests,
        total_tokens_limit=system_tokens,
    )


def _import_agent_module(agent_name: str) -> Any:
    """Dynamically import an agent module from the registry."""
    registry = get_registry()
    module_path = registry.resolve_module_path(agent_name)
    return importlib.import_module(module_path)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _resolve_agent(session: "SessionResponse", message: str) -> str:
    """Determine which agent handles this message.

    Priority: session.agent_id > keyword routing > fallback.
    """
    registry = get_registry()

    if session.agent_id and registry.has(session.agent_id):
        return session.agent_id

    router = RuleBasedRouter(registry)
    request = MissionControlRequest(user_input=message)
    agent_name = router.route(request)

    if agent_name is not None:
        return agent_name

    mc_config = _load_mission_control_config()
    fallback = mc_config.routing.fallback_agent
    if fallback and registry.has(fallback):
        return fallback

    available = ", ".join(c["agent_name"] for c in registry.list_all()) or "none"
    raise ValidationError(f"No agent matched. Available agents: {available}.")


# ---------------------------------------------------------------------------
# Event / persistence plumbing
# ---------------------------------------------------------------------------


async def _publish(event_bus: EventBusProtocol, event: SessionEvent) -> None:
    """Publish event to bus. Non-critical — NoOpEventBus silently drops."""
    try:
        await event_bus.publish(event)
    except (OSError, RuntimeError):
        logger.debug("Event bus publish failed", exc_info=True)


async def _persist_messages(
    session_service: SessionServiceProtocol,
    session_id: str,
    creates: list[SessionMessageCreate],
) -> None:
    """Persist messages to session. Non-critical."""
    try:
        for create in creates:
            await session_service.add_message(session_id, create)
    except (OSError, ApplicationError) as exc:
        logger.warning("Failed to persist session messages: %s", exc)


# ---------------------------------------------------------------------------
# Mission dispatch helpers (Plan 13)
# ---------------------------------------------------------------------------


def _build_roster_prompt(roster: Roster) -> str:
    """Format roster for the Planning Agent's context."""
    lines = ["## Available Agents\n"]
    for agent in roster.agents:
        lines.append(f"### {agent.agent_name} (v{agent.agent_version})")
        lines.append(f"**Description:** {agent.description}")
        lines.append(f"**Model:** {agent.model.name}")
        lines.append(f"**Tools:** {', '.join(agent.tools) if agent.tools else 'none'}")
        lines.append(f"**Input contract:** {agent.interface.input}")
        lines.append(f"**Output contract:** {agent.interface.output}")
        lines.append(
            f"**Constraints:** timeout={agent.constraints.timeout_seconds}s, "
            f"cost_ceiling=${agent.constraints.cost_ceiling_usd}, "
            f"retry_budget={agent.constraints.retry_budget}"
        )
        lines.append("")
    return "\n".join(lines)


def _build_planning_prompt(
    mission_brief: str,
    mission_id: str,
    roster_description: str,
    upstream_context: dict | None,
    code_map: dict | None = None,
    project_context: dict | None = None,
    recent_failures: list | None = None,
) -> str:
    """Assemble the full prompt for the Planning Agent.

    Includes project context (PCD) and recent failure history when available,
    so the planner can make informed decomposition decisions.
    """
    parts = [
        f"## Mission Brief\n\n{mission_brief}\n",
        f"## Mission ID\n\n{mission_id}\n",
        roster_description,
    ]

    if project_context:
        parts.append(
            "## Project Context\n\n"
            "The following is the Project Context Document (PCD) for the target project. "
            "Use it to understand the project's architecture, constraints, current state, "
            "and key decisions when decomposing tasks.\n\n"
            f"```json\n{json.dumps(project_context, indent=2)}\n```\n"
        )

    if recent_failures:
        parts.append(
            "## Recent Failures (Avoid Repeating)\n\n"
            "The following tasks failed in recent runs against this project. "
            "Account for these when planning — e.g., split large modules that "
            "caused token limits, avoid approaches that timed out, adjust task "
            "granularity based on past outcomes.\n\n"
            f"```json\n{json.dumps(recent_failures, indent=2)}\n```\n"
        )

    if upstream_context:
        parts.append(
            f"## Upstream Context\n\n```json\n"
            f"{json.dumps(upstream_context, indent=2)}\n```\n"
        )

    if code_map:
        parts.append(
            "## Code Map (Structural Overview)\n\n"
            "The following JSON contains the complete structural map of the codebase.\n"
            "Use it to:\n"
            "- Identify which files exist and what they contain\n"
            "- Trace dependencies via the import_graph\n"
            "- Generate file_manifest entries for coding tasks\n"
            "- Understand which modules are most important (highest PageRank rank)\n\n"
            "```json\n"
            f"{json.dumps(code_map, indent=None)}\n"
            "```\n"
        )

    parts.append(
        "## Output Format\n\n"
        "Return your task plan as JSON within <task_plan> tags.\n"
        "Follow the TaskPlan schema exactly. See system prompt for rules.\n"
    )

    return "\n".join(parts)


def _append_validation_feedback(prompt: str, errors: list[str]) -> str:
    """Append validation errors to planning prompt for retry."""
    error_text = "\n".join(f"- {e}" for e in errors)
    return (
        f"{prompt}\n\n"
        f"--- VALIDATION ERRORS FROM PREVIOUS ATTEMPT ---\n"
        f"Your previous TaskPlan failed validation:\n{error_text}\n"
        f"Fix these errors and try again.\n"
    )


def _make_agent_executor(
    session_service: SessionServiceProtocol, event_bus: EventBusProtocol,
) -> ExecuteAgentFn:
    """Create the execute_agent_fn closure for the dispatch loop."""

    async def execute_agent(
        agent_name: str,
        instructions: str,
        inputs: dict,
        usage_limits: UsageLimits,
    ) -> dict:
        """Execute a single agent through the standard path.

        Calls agent.run() directly (not module.run_agent()) so we can
        extract usage from the AgentRunResult before it's unwrapped.
        """
        registry = get_registry()
        agent_config = registry.get(agent_name)
        if agent_config is None:
            raise ValidationError(f"Agent '{agent_name}' not found in registry")

        module = _import_agent_module(agent_name)
        model = _build_model(agent_config.model)
        agent = module.create_agent(model)
        deps = _build_agent_deps(agent_name, agent_config)

        # Merge inputs into the user message so the agent sees them
        user_message = instructions
        if inputs:
            user_message = (
                f"{instructions}\n\n"
                f"## Inputs\n\n```json\n"
                f"{json.dumps(inputs, indent=2, default=str)}\n```"
            )

        # QA agent: pre-compute PQI deterministically and enrich message
        pqi_data = None
        if agent_name == "code.quality.agent" and hasattr(module, "_compute_pqi"):
            pqi_data = await module._compute_pqi(deps)
            if pqi_data and hasattr(module, "_format_pqi_for_llm"):
                pqi_text = module._format_pqi_for_llm(pqi_data)
                user_message = (
                    f"{user_message}\n\n"
                    f"## Pre-computed PQI (PyQuality Index)\n\n"
                    f"The following PQI score has been computed deterministically. "
                    f"Reference it in your summary and recommendations — you do NOT "
                    f"need to call run_quality_score_tool yourself.\n\n"
                    f"{pqi_text}"
                )

        # Call agent.run() directly to retain usage metadata
        run_result = await agent.run(
            user_message, deps=deps, usage_limits=usage_limits,
        )

        # Extract output
        output = run_result.output

        # QA agent: inject PQI deterministically before serialization
        if pqi_data and hasattr(output, "pqi"):
            output.pqi = pqi_data

        if hasattr(output, "model_dump"):
            output_dict = output.model_dump()
        elif isinstance(output, dict):
            output_dict = output
        else:
            output_dict = {"result": str(output)}

        # Extract usage from the AgentRunResult
        usage = run_result.usage()
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
        model_name = _get_model_name(agent_config.model)
        cost_usd = compute_cost_usd(input_tokens, output_tokens, model_name)

        output_dict["_meta"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "thinking_tokens": 0,
            "cost_usd": cost_usd,
        }

        return output_dict

    return execute_agent


async def _call_planning_agent(
    prompt: str,
    roster: Roster,
    upstream_context: dict | None,
) -> dict:
    """Call the Planning Agent and return the raw result.

    Loads the Code Map (regenerating if stale) and injects it into both
    the planning prompt and PlanningAgentDeps.
    """
    from modules.backend.agents.horizontal.planning.agent import (
        PlanningAgentDeps,
        create_agent,
        run_agent,
    )
    from modules.backend.services.code_map.loader import CodeMapLoader

    project_root = find_project_root()

    # Load Code Map, regenerating if stale or missing
    loader = CodeMapLoader(project_root)
    code_map = loader.ensure_fresh()

    registry = get_registry()
    planning_cfg = registry.get("horizontal.planning.agent")
    config = {
        "model": _get_model_name(planning_cfg.model),
    }
    agent = create_agent(config)

    roster_desc = _build_roster_prompt(roster)
    planning_prompt = _build_planning_prompt(
        mission_brief=prompt,
        mission_id="pending",
        roster_description=roster_desc,
        upstream_context=upstream_context,
        code_map=code_map,
    )

    deps = PlanningAgentDeps(
        project_root=project_root,
        scope=FileScope(read_paths=[], write_paths=[]),
        mission_brief=prompt,
        roster_description=roster_desc,
        upstream_context=upstream_context,
        code_map=code_map,
    )

    return await run_agent(agent, deps, planning_prompt)
