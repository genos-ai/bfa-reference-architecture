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


PLANNING_AGENT_NAME = "horizontal.planning.agent"
VERIFICATION_AGENT_NAME = "horizontal.verification.agent"


def load_roster(roster_name: str = "default") -> Roster:
    """Load and validate a roster from YAML.

    Planning and verification agents must be defined in the roster YAML.
    Raises ValueError if either is missing.
    """
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

    # Validate required infrastructure agents are present in YAML
    missing = []
    if not roster.get_agent_by_name(PLANNING_AGENT_NAME):
        missing.append(PLANNING_AGENT_NAME)
    if not roster.get_agent_by_name(VERIFICATION_AGENT_NAME):
        missing.append(VERIFICATION_AGENT_NAME)
    if missing:
        raise ValueError(
            f"Roster '{roster_name}' is missing required agents: "
            f"{', '.join(missing)}. Add them to {roster_path}."
        )

    logger.info(
        "Roster loaded",
        extra={
            "roster": roster_name,
            "agent_count": len(roster.agents),
            "agents": roster.agent_names,
        },
    )
    return roster
