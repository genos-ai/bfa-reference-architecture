"""
CLI handler for --service agent.

Send a message to an agent via Mission Control single-agent routing.
Creates an ephemeral session, dispatches, and prints the result.
"""

import asyncio
import json
import sys

import click

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def run_agent(cli_logger, message: str, agent: str | None) -> None:
    """Send a message to an agent and print the result."""
    cli_logger.info(
        "Agent dispatch",
        extra={"message_preview": message[:80], "agent": agent},
    )

    click.echo(f"Sending to {'agent: ' + agent if agent else 'Mission Control router'}...")
    click.echo()

    try:
        result = asyncio.run(_dispatch(message, agent))
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        cli_logger.error("Agent dispatch failed", extra={"error": str(e)})
        sys.exit(1)

    _print_result(result)


async def _dispatch(message: str, agent: str | None) -> dict:
    """Run agent dispatch with a real DB session."""
    from modules.backend.core.database import get_async_session
    from modules.backend.agents.mission_control.mission_control import collect
    from modules.backend.services.session import SessionService
    from modules.backend.schemas.session import SessionCreate

    async with get_async_session() as db:
        service = SessionService(db)
        session = await service.create_session(
            SessionCreate(agent_id=agent, goal=message[:200]),
        )
        session_id = session.id

        result = await collect(
            session_id,
            message,
            session_service=service,
        )
        await db.commit()

        # Fetch updated session for cost info
        session = await service.get_session(session_id)

        return {
            "agent_name": result.get("agent_name", ""),
            "output": result.get("output", ""),
            "session_id": session_id,
            "input_tokens": session.total_input_tokens,
            "output_tokens": session.total_output_tokens,
            "cost_usd": session.total_cost_usd,
        }


def _print_result(result: dict) -> None:
    """Pretty-print agent response."""
    click.echo(click.style(f"Agent: {result['agent_name']}", fg="cyan", bold=True))
    click.echo(click.style(f"Session: {result['session_id']}", dim=True))
    click.echo()

    # Try to pretty-print JSON output
    raw = result["output"]
    try:
        parsed = json.loads(raw)
        click.echo(json.dumps(parsed, indent=2))
    except (json.JSONDecodeError, TypeError):
        click.echo(raw)

    click.echo()
    click.echo(
        click.style(
            f"Tokens: {result['input_tokens']:,} in / {result['output_tokens']:,} out  "
            f"Cost: ${result['cost_usd']:.4f}",
            dim=True,
        )
    )
