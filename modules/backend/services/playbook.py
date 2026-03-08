"""
Playbook Service.

Loads playbook YAML files from config/playbooks/, validates against
PlaybookSchema, resolves capability references to agent names, and
generates Mission briefs from playbook steps.

This service is stateless — it reads from the filesystem and agent
registry. It does not touch the database.
"""

from pathlib import Path
from typing import Any

import yaml

from modules.backend.core.config import find_project_root, get_app_config
from modules.backend.core.logging import get_logger
from modules.backend.schemas.playbook import PlaybookSchema, PlaybookStepSchema

logger = get_logger(__name__)


class PlaybookService:
    """Load, validate, and resolve playbooks from config/playbooks/."""

    def __init__(self, agent_registry: dict[str, Any] | None = None) -> None:
        self._project_root = find_project_root()
        self._agent_registry = agent_registry
        self._playbooks: dict[str, PlaybookSchema] = {}

    def load_playbooks(self) -> dict[str, PlaybookSchema]:
        """Load all playbook YAML files from the configured directory.

        Scans recursively for *.yaml files, validates each against
        PlaybookSchema, and returns a dict keyed by playbook_name.
        Invalid playbooks are logged and skipped (not fatal).
        """
        app_config = get_app_config()
        playbooks_dir = self._project_root / app_config.playbooks.playbooks_dir

        if not playbooks_dir.exists():
            logger.warning(
                "Playbooks directory not found",
                extra={"path": str(playbooks_dir)},
            )
            return {}

        loaded: dict[str, PlaybookSchema] = {}

        for yaml_path in sorted(playbooks_dir.rglob("*.yaml")):
            try:
                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if not raw or not isinstance(raw, dict):
                    continue

                playbook = PlaybookSchema(**raw)

                if playbook.playbook_name in loaded:
                    logger.warning(
                        "Duplicate playbook name, skipping",
                        extra={
                            "playbook_name": playbook.playbook_name,
                            "path": str(yaml_path),
                        },
                    )
                    continue

                max_steps = app_config.playbooks.max_steps_per_playbook
                if len(playbook.steps) > max_steps:
                    logger.warning(
                        "Playbook exceeds max steps, skipping",
                        extra={
                            "playbook_name": playbook.playbook_name,
                            "step_count": len(playbook.steps),
                            "max_steps": max_steps,
                        },
                    )
                    continue

                max_budget = app_config.playbooks.max_budget_usd
                if playbook.budget.max_cost_usd > max_budget:
                    logger.warning(
                        "Playbook budget exceeds system cap, capping",
                        extra={
                            "playbook_name": playbook.playbook_name,
                            "requested": playbook.budget.max_cost_usd,
                            "capped_to": max_budget,
                        },
                    )
                    playbook.budget.max_cost_usd = max_budget

                loaded[playbook.playbook_name] = playbook
                logger.debug(
                    "Playbook loaded",
                    extra={
                        "playbook_name": playbook.playbook_name,
                        "version": playbook.version,
                        "steps": len(playbook.steps),
                        "enabled": playbook.enabled,
                    },
                )

            except Exception as e:
                logger.warning(
                    "Failed to load playbook",
                    extra={"path": str(yaml_path), "error": str(e)},
                )
                continue

        self._playbooks = loaded
        logger.info(
            "Playbooks loaded",
            extra={"count": len(loaded), "names": list(loaded.keys())},
        )
        return loaded

    def list_playbooks(self, enabled_only: bool = True) -> list[PlaybookSchema]:
        """List available playbooks."""
        if not self._playbooks:
            self.load_playbooks()

        playbooks = list(self._playbooks.values())
        if enabled_only:
            playbooks = [p for p in playbooks if p.enabled]
        return playbooks

    def get_playbook(self, playbook_name: str) -> PlaybookSchema | None:
        """Get a specific playbook by name."""
        if not self._playbooks:
            self.load_playbooks()
        return self._playbooks.get(playbook_name)

    def resolve_capability(self, capability: str) -> str:
        """Resolve a capability string to an agent name.

        Convention: capability 'content.summarizer' resolves to
        agent 'content.summarizer.agent'.

        Raises:
            ValueError: If no agent found for the capability.
        """
        agent_name = f"{capability}.agent"

        if self._agent_registry is not None:
            if agent_name not in self._agent_registry:
                raise ValueError(
                    f"No agent found for capability '{capability}' "
                    f"(expected agent '{agent_name}' in registry)"
                )
            agent_config = self._agent_registry[agent_name]
            if not agent_config.get("enabled", True):
                raise ValueError(
                    f"Agent '{agent_name}' for capability '{capability}' "
                    f"is disabled"
                )
            return agent_name

        # Fallback: scan config/agents/ for the agent YAML
        agents_dir = self._project_root / "config" / "agents"
        if not agents_dir.exists():
            raise ValueError(
                f"No agent found for capability '{capability}' "
                f"(agents directory not found)"
            )

        for yaml_path in agents_dir.rglob("agent.yaml"):
            try:
                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if raw and raw.get("agent_name") == agent_name:
                    if not raw.get("enabled", True):
                        raise ValueError(
                            f"Agent '{agent_name}' for capability "
                            f"'{capability}' is disabled"
                        )
                    return agent_name
            except yaml.YAMLError:
                continue

        raise ValueError(
            f"No agent found for capability '{capability}' "
            f"(expected agent '{agent_name}')"
        )

    def validate_playbook_capabilities(
        self, playbook: PlaybookSchema,
    ) -> list[str]:
        """Validate that all capabilities in a playbook resolve to agents.

        Returns list of error messages. Empty list means all resolve.
        """
        errors: list[str] = []
        for step in playbook.steps:
            try:
                self.resolve_capability(step.capability)
            except ValueError as e:
                errors.append(f"Step '{step.id}': {e}")
        return errors

    def generate_mission_briefs(
        self, playbook: PlaybookSchema,
    ) -> list[dict[str, Any]]:
        """Convert playbook steps into Mission brief definitions."""
        step_index_map: dict[str, int] = {}
        for i, step in enumerate(playbook.steps):
            step_index_map[step.id] = i

        briefs: list[dict[str, Any]] = []
        app_config = get_app_config()

        for i, step in enumerate(playbook.steps):
            agent_name = self.resolve_capability(step.capability)

            brief: dict[str, Any] = {
                "step_id": step.id,
                "objective": step.description or f"Execute: {step.id}",
                "primary_capability": step.capability,
                "resolved_agent": agent_name,
                "roster_ref": step.roster,
                "complexity_tier": step.complexity_tier,
                "cost_ceiling_usd": (
                    step.cost_ceiling_usd
                    or app_config.playbooks.default_budget_usd
                ),
                "environment": step.environment,
                "input_context": dict(step.input),
                "output_mapping": (
                    step.output_mapping.model_dump()
                    if step.output_mapping
                    else None
                ),
                "timeout_seconds": (
                    step.timeout_seconds
                    or app_config.playbooks.default_step_timeout_seconds
                ),
                "dependencies": [
                    {
                        "depends_on_step": dep_id,
                        "depends_on_index": step_index_map.get(dep_id),
                    }
                    for dep_id in step.depends_on
                ],
                "sort_order": i,
            }
            briefs.append(brief)

        return briefs

    def match_playbook(self, user_input: str) -> PlaybookSchema | None:
        """Match user input against playbook trigger patterns.

        Used by Mission Control for deterministic fast-path routing (P2).
        """
        if not self._playbooks:
            self.load_playbooks()

        input_lower = user_input.lower()

        for playbook in self._playbooks.values():
            if not playbook.enabled:
                continue
            if not playbook.trigger.match_patterns:
                continue

            for pattern in playbook.trigger.match_patterns:
                if pattern.lower() in input_lower:
                    logger.info(
                        "Playbook matched by pattern",
                        extra={
                            "playbook_name": playbook.playbook_name,
                            "pattern": pattern,
                        },
                    )
                    return playbook

        return None

    def resolve_upstream_context(
        self,
        step: PlaybookStepSchema,
        completed_outcomes: dict[str, dict],
        playbook_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build upstream_context for a Mission from completed prior missions.

        The Playbook is the anti-corruption layer: it extracts specific
        fields from prior MissionOutcomes via output_mapping and merges
        them with the playbook's initial context.
        """
        upstream: dict[str, Any] = dict(playbook_context)

        for dep_id in step.depends_on:
            if dep_id in completed_outcomes:
                upstream.update(completed_outcomes[dep_id])

        # Resolve @context.* references in step input
        resolved_input: dict[str, Any] = {}
        for key, value in step.input.items():
            if isinstance(value, str) and value.startswith("@context."):
                context_key = value[len("@context."):]
                if context_key in upstream:
                    resolved_input[key] = upstream[context_key]
                else:
                    logger.warning(
                        "Unresolved @context reference in step input",
                        extra={
                            "step_id": step.id,
                            "reference": value,
                            "available_keys": list(upstream.keys()),
                        },
                    )
                    resolved_input[key] = value
            else:
                resolved_input[key] = value

        upstream["_step_input"] = resolved_input
        return upstream
