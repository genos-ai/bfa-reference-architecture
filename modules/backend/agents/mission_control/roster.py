"""Agent roster loader and validator.

The roster defines which agents are available for Mission Control dispatch.
Static per Mission Control type, loaded from YAML at startup.
Planning Agent and Verification Agent are auto-included in every roster.
"""

import yaml
from pydantic import BaseModel, ConfigDict, Field

from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class RosterModelSchema(BaseModel):
    """Pinned model config within a roster entry."""

    model_config = ConfigDict(extra="forbid")

    name: str
    temperature: float = 0.0
    max_tokens: int = 4096


class RosterInterfaceSchema(BaseModel):
    """Typed I/O contract within a roster entry."""

    model_config = ConfigDict(extra="forbid")

    input: dict[str, str] = Field(default_factory=dict)
    output: dict[str, str] = Field(default_factory=dict)


class RosterConstraintsSchema(BaseModel):
    """Execution constraints within a roster entry."""

    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = 120
    cost_ceiling_usd: float = 1.0
    retry_budget: int = 2
    parallelism: str = "safe"


class RosterAgentEntry(BaseModel):
    """A single agent in the roster."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    agent_version: str
    description: str
    model: RosterModelSchema
    tools: list[str] = Field(default_factory=list)
    interface: RosterInterfaceSchema
    constraints: RosterConstraintsSchema = Field(
        default_factory=RosterConstraintsSchema,
    )


class Roster(BaseModel):
    """Complete agent roster for a Mission Control instance."""

    model_config = ConfigDict(extra="forbid")

    agents: list[RosterAgentEntry]

    def get_agent(self, name: str, version: str) -> RosterAgentEntry | None:
        """Look up agent by name and version. Returns None if not found."""
        for agent in self.agents:
            if agent.agent_name == name and agent.agent_version == version:
                return agent
        return None

    def get_agent_by_name(self, name: str) -> RosterAgentEntry | None:
        """Look up agent by name only (latest version). Returns None if not found."""
        for agent in self.agents:
            if agent.agent_name == name:
                return agent
        return None

    @property
    def agent_names(self) -> list[str]:
        """All agent names in the roster."""
        return [a.agent_name for a in self.agents]


PLANNING_AGENT_ENTRY = RosterAgentEntry(
    agent_name="horizontal.planning.agent",
    agent_version="1.0.0",
    description="Decomposes mission briefs into executable task plans.",
    model=RosterModelSchema(
        name="anthropic:claude-opus-4-20250514",
        temperature=0.0,
        max_tokens=16384,
    ),
    tools=[],
    interface=RosterInterfaceSchema(
        input={
            "mission_brief": "string",
            "roster": "object",
            "upstream_context": "object",
        },
        output={"task_plan": "object"},
    ),
    constraints=RosterConstraintsSchema(
        timeout_seconds=300,
        cost_ceiling_usd=5.0,
        retry_budget=2,
        parallelism="unsafe",
    ),
)

VERIFICATION_AGENT_ENTRY = RosterAgentEntry(
    agent_name="horizontal.verification.agent",
    agent_version="1.0.0",
    description="Evaluates agent output quality against criteria. Used in Tier 3 verification.",
    model=RosterModelSchema(
        name="anthropic:claude-opus-4-20250514",
        temperature=0.0,
        max_tokens=8192,
    ),
    tools=[],
    interface=RosterInterfaceSchema(
        input={
            "task_instructions": "string",
            "evaluation_criteria": "list[string]",
            "agent_output": "object",
        },
        output={
            "overall_score": "float",
            "pass": "bool",
            "criteria_results": "list[object]",
        },
    ),
    constraints=RosterConstraintsSchema(
        timeout_seconds=180,
        cost_ceiling_usd=3.0,
        retry_budget=1,
        parallelism="unsafe",
    ),
)


def load_roster(roster_name: str = "default") -> Roster:
    """Load and validate a roster from YAML. Auto-includes planning and verification agents."""
    roster_path = (
        find_project_root()
        / "config"
        / "mission_control"
        / "rosters"
        / f"{roster_name}.yaml"
    )
    if not roster_path.exists():
        raise FileNotFoundError(f"Roster not found: {roster_path}")

    with open(roster_path) as f:
        raw = yaml.safe_load(f)

    roster = Roster.model_validate(raw)

    # Auto-include planning and verification agents if not already present
    if not roster.get_agent_by_name(PLANNING_AGENT_ENTRY.agent_name):
        roster.agents.append(PLANNING_AGENT_ENTRY)
    if not roster.get_agent_by_name(VERIFICATION_AGENT_ENTRY.agent_name):
        roster.agents.append(VERIFICATION_AGENT_ENTRY)

    logger.info(
        "Roster loaded",
        extra={
            "roster": roster_name,
            "agent_count": len(roster.agents),
            "agents": roster.agent_names,
        },
    )
    return roster
