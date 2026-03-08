"""Mission Control shared helpers — agent building, routing, event plumbing.

Private infrastructure extracted from mission_control.py to keep files
under the 500-line target.  Everything here is an implementation detail;
the public API lives in mission_control.py.
"""

import importlib
import json
from typing import Any

from pydantic_ai import UsageLimits
from pydantic_ai.models import Model

from modules.backend.agents.config_schema import AgentConfigSchema, AgentModelSchema
from modules.backend.agents.deps.base import (
    BaseAgentDeps,
    FileScope,
    HealthAgentDeps,
    QaAgentDeps,
)
from modules.backend.agents.mission_control.middleware import _load_mission_control_config
from modules.backend.agents.mission_control.models import MissionControlRequest
from modules.backend.agents.mission_control.registry import get_registry
from modules.backend.agents.mission_control.roster import Roster
from modules.backend.agents.mission_control.router import RuleBasedRouter
from modules.backend.core.config import find_project_root, get_app_config, get_settings
from modules.backend.core.logging import get_logger
from modules.backend.events.types import SessionEvent
from modules.backend.schemas.session import SessionMessageCreate
from modules.backend.services.session import SessionService

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
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        bare_name = model_name.split(":", 1)[1]
        provider = AnthropicProvider(api_key=settings.anthropic_api_key)
        return AnthropicModel(bare_name, provider=provider)

    raise ValueError(f"Unsupported model provider in '{model_name}'. Expected 'anthropic:model_name'.")


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


def _get_usage_limits() -> UsageLimits:
    """Build UsageLimits from mission_control.yaml."""
    config = _load_mission_control_config()
    return UsageLimits(
        request_limit=config.limits.max_requests_per_task,
        total_tokens_limit=config.limits.max_tokens_per_task,
    )


def _import_agent_module(agent_name: str) -> Any:
    """Dynamically import an agent module from the registry."""
    registry = get_registry()
    module_path = registry.resolve_module_path(agent_name)
    return importlib.import_module(module_path)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _resolve_agent(session: Any, message: str) -> str:
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
    raise ValueError(f"No agent matched. Available agents: {available}.")


# ---------------------------------------------------------------------------
# Event / persistence plumbing
# ---------------------------------------------------------------------------


async def _publish(event_bus: Any, event: SessionEvent) -> None:
    """Publish event to bus if available. Non-critical."""
    if event_bus is None:
        return
    try:
        await event_bus.publish(event)
    except Exception:
        logger.debug("Event bus publish failed", exc_info=True)


async def _persist_messages(
    session_service: SessionService,
    session_id: str,
    creates: list[SessionMessageCreate],
) -> None:
    """Persist messages to session. Non-critical."""
    try:
        for create in creates:
            await session_service.add_message(session_id, create)
    except Exception:
        logger.warning("Failed to persist session messages", exc_info=True)


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
) -> str:
    """Assemble the full prompt for the Planning Agent."""
    parts = [
        f"## Mission Brief\n\n{mission_brief}\n",
        f"## Mission ID\n\n{mission_id}\n",
        roster_description,
    ]

    if upstream_context:
        parts.append(
            f"## Upstream Context\n\n```json\n"
            f"{json.dumps(upstream_context, indent=2)}\n```\n"
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


def _make_agent_executor(session_service: Any, event_bus: Any | None) -> Any:
    """Create the execute_agent_fn closure for the dispatch loop."""
    from modules.backend.agents.mission_control.cost import compute_cost_usd

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
            raise ValueError(f"Agent '{agent_name}' not found in registry")

        module = _import_agent_module(agent_name)
        model = _build_model(agent_config.model)
        agent = module.create_agent(model)
        deps = _build_agent_deps(agent_name, agent_config)

        # Call agent.run() directly to retain usage metadata
        run_result = await agent.run(
            instructions, deps=deps, usage_limits=usage_limits,
        )

        # Extract output
        output = run_result.output
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
    """Call the Planning Agent and return the raw result."""
    from modules.backend.agents.horizontal.planning.agent import (
        PlanningAgentDeps,
        create_agent,
        run_agent,
    )

    config = {
        "model": "anthropic:claude-opus-4-20250514",
    }
    agent = create_agent(config)
    deps = PlanningAgentDeps(
        project_root=find_project_root(),
        scope=FileScope(read_paths=[], write_paths=[]),
        mission_brief=prompt,
        roster_description=_build_roster_prompt(roster),
        upstream_context=upstream_context,
    )

    return await run_agent(agent, deps, prompt)
