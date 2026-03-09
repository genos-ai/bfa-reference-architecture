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


def show_agents(cli_logger) -> None:
    """List all registered agents."""
    from modules.backend.agents.mission_control.mission_control import list_agents

    agents = list_agents()

    if not agents:
        click.echo("No agents registered.")
        return

    from modules.backend.cli.report import DOTTED_ROWS, build_table, get_console

    table = build_table("Available Agents", columns=[
        ("Agent",       {"style": "cyan", "width": 26}),
        ("Description", {"ratio": 2, "no_wrap": False}),
        ("Tools",       {"style": "green", "ratio": 2, "no_wrap": False}),
        ("Folders",     {"style": "dim", "width": 20, "no_wrap": False}),
    ], show_lines=True, table_box=DOTTED_ROWS)

    for agent in agents:
        tools = ", ".join(agent.get("tools", []))
        scope = agent.get("scope", {})
        read_paths = scope.get("read", [])
        write_paths = scope.get("write", [])
        folder_parts = []
        if read_paths:
            folder_parts.append(f"R: {', '.join(read_paths)}")
        if write_paths:
            folder_parts.append(f"W: {', '.join(write_paths)}")
        folders = "\n".join(folder_parts) if folder_parts else "-"
        table.add_row(
            agent["agent_name"],
            agent.get("description", ""),
            tools,
            folders,
        )

    get_console().print(table)
    cli_logger.info("Listed agents", extra={"count": len(agents)})


def run_agent(cli_logger, message: str, agent: str | None, output_format: str = "human") -> None:
    """Send a message to an agent and print the result."""
    cli_logger.info(
        "Agent dispatch",
        extra={"message_preview": message[:80], "agent": agent},
    )

    target = agent or "Mission Control router"

    if output_format in ("human", "json"):
        from modules.backend.cli.report import get_console

        console = get_console()
        with console.status(f"[cyan]Sending to {target}...[/cyan]", spinner="dots"):
            try:
                result = asyncio.run(_dispatch(message, agent))
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                cli_logger.error("Agent dispatch failed", extra={"error": str(e)})
                sys.exit(1)
        if output_format == "human":
            _print_human(result, console)
        else:
            _print_result(result, console)
    else:
        try:
            result = asyncio.run(_dispatch(message, agent))
        except Exception as e:
            click.echo(json.dumps({"error": str(e)}, separators=(",", ":")))
            cli_logger.error("Agent dispatch failed", extra={"error": str(e)})
            sys.exit(1)
        _print_jsonl(result)


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
            "thinking": result.get("thinking"),
            "session_id": session_id,
            "input_tokens": session.total_input_tokens,
            "output_tokens": session.total_output_tokens,
            "cost_usd": session.total_cost_usd,
        }


def _print_jsonl(result: dict) -> None:
    """Emit JSONL: summary line first, then one line per data item.

    If the agent output is JSON containing a top-level list field
    (e.g. "violations", "findings", "results"), each item in that
    list is emitted as its own JSONL line. The summary line contains
    everything else (metadata, scalar fields, thinking).
    """
    _dump = lambda obj: click.echo(json.dumps(obj, separators=(",", ":"), default=str))

    raw = result["output"]
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = None

    # Build summary from non-output fields
    summary = {
        "type": "summary",
        "agent_name": result["agent_name"],
        "session_id": result["session_id"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "cost_usd": result["cost_usd"],
    }
    if result.get("thinking"):
        summary["thinking"] = result["thinking"]

    # Find and extract a top-level list field from parsed output
    items_key = None
    items: list = []
    if isinstance(parsed, dict):
        for key, val in parsed.items():
            if isinstance(val, list):
                items_key = key
                items = val
                break
        # Merge scalar fields into summary
        for key, val in parsed.items():
            if key != items_key:
                summary[key] = val

    _dump(summary)

    # Emit each item as its own line
    for item in items:
        if isinstance(item, dict):
            item["type"] = items_key or "item"
        _dump(item)


def _print_human(result: dict, console) -> None:
    """Human-friendly output — shape-detected tables instead of raw JSON."""
    from modules.backend.cli.report import (
        render_human,
        summary_table,
        thinking_panel,
    )

    thinking = result.get("thinking")
    if thinking:
        console.print(thinking_panel(thinking))

    for renderable in render_human(
        result["output"],
        title=result["agent_name"],
        subtitle=f"session {result['session_id']}",
    ):
        console.print(renderable)

    console.print(summary_table(
        agent_name=result["agent_name"],
        session_id=result["session_id"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cost_usd=result["cost_usd"],
    ))


def _print_result(result: dict, console) -> None:
    """Pretty-print agent response using shared Rich primitives."""
    from modules.backend.cli.report import (
        format_json_body,
        output_panel,
        summary_table,
        thinking_panel,
    )

    thinking = result.get("thinking")
    if thinking:
        console.print(thinking_panel(thinking))

    console.print(output_panel(
        format_json_body(result["output"]),
        title=result["agent_name"],
        subtitle=f"session {result['session_id']}",
    ))

    console.print(summary_table(
        agent_name=result["agent_name"],
        session_id=result["session_id"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cost_usd=result["cost_usd"],
    ))
