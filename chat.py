#!/usr/bin/env python3
"""
Agent Chat Client.

Single-shot CLI for sending messages to platform agents.
Designed for AI agents, scripts, and CI pipelines.

Usage:
    python chat.py --help
    python chat.py --message "check system health"
    python chat.py --message "check system health" --raw
    python chat.py --message "check system health" --verbose
    python chat.py --ping
    python chat.py --port 8099 --message "check health"
"""

import asyncio
import json
import sys
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.core.config import get_server_base_url, validate_project_root
from modules.backend.core.logging import bind_context, get_logger, setup_logging


async def send_message(base_url: str, timeout: float, message: str, agent: str | None, raw: bool, verbose: bool) -> int:
    """Send a message to the agent coordinator and display the response."""
    import httpx

    payload: dict = {"message": message}
    if agent:
        payload["agent"] = agent

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        headers={"X-Frontend-ID": "cli"},
    ) as client:
        try:
            response = await client.post(
                "/api/v1/agents/chat",
                json=payload,
            )
        except httpx.ConnectError:
            click.echo(click.style("Error: Backend is not reachable.", fg="red"), err=True)
            click.echo("Start it with: python cli.py --service server", err=True)
            return 1

    if raw:
        click.echo(json.dumps(response.json(), indent=2))
        return 0 if response.status_code == 200 else 1

    if response.status_code != 200:
        error = response.json().get("error", {})
        click.echo(click.style(f"Error: {error.get('message', response.text)}", fg="red"), err=True)
        return 1

    data = response.json().get("data", {})
    agent_name = data.get("agent_name", "agent")
    output = data.get("output", "No response")
    components = data.get("components")
    advice = data.get("advice")

    if verbose:
        click.echo(click.style(f"[{agent_name}] ", fg="green", bold=True), nl=False)
    click.echo(output)

    if components and verbose:
        for comp, status in components.items():
            color = "green" if "healthy" in status.lower() else "red" if "unhealthy" in status.lower() else "yellow"
            click.echo(f"  {click.style('●', fg=color)} {comp}: {status}")

    if advice and verbose:
        click.echo(click.style(f"\nAdvice: {advice}", dim=True))

    return 0


async def send_message_stream(base_url: str, message: str, agent: str | None, raw: bool, verbose: bool) -> int:
    """Interactive agent conversation via SSE streaming.

    Sends a message, displays streaming progress and results.
    If the agent needs human decisions, prompts for input and
    continues the conversation until done.
    """
    import httpx

    conversation_id = None
    current_message = message

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=None,
        headers={"X-Frontend-ID": "cli"},
    ) as client:
        while True:
            payload: dict = {"message": current_message}
            if agent:
                payload["agent"] = agent
            if conversation_id:
                payload["conversation_id"] = conversation_id

            try:
                result_data = None
                async with client.stream(
                    "POST",
                    "/api/v1/agents/chat/stream",
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        click.echo(click.style(f"Error: {response.text}", fg="red"), err=True)
                        return 1

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        event_type = event.get("type")

                        if event_type == "tool_start":
                            if verbose:
                                click.echo(click.style(f"  → {event['tool']}...", dim=True))
                        elif event_type == "tool_done":
                            detail = event.get("detail", "")
                            if verbose:
                                click.echo(click.style(f"  ✓ {event['tool']} ({detail})", fg="green"))
                        elif event_type == "complete":
                            result_data = event.get("result", {})
                            conversation_id = event.get("conversation_id")

            except httpx.ConnectError:
                click.echo(click.style("Error: Backend is not reachable.", fg="red"), err=True)
                click.echo("Start it with: python cli.py --service server", err=True)
                return 1

            if result_data is None:
                click.echo(click.style("Error: No result received", fg="red"), err=True)
                return 1

            if raw:
                click.echo(json.dumps(result_data, indent=2))
                return 0

            _display_qa_result(result_data)

            needs_human = result_data.get("needs_human_count", 0)
            if needs_human == 0:
                return 0

            click.echo()
            click.echo(click.style(
                f"{needs_human} violation(s) need your decision. "
                "Type your response, or 'done' to exit.",
                bold=True,
            ))
            click.echo()

            try:
                user_response = click.prompt("You", prompt_suffix="> ")
            except (click.Abort, EOFError):
                return 0

            if user_response.strip().lower() in ("done", "exit", "quit", "q"):
                return 0

            current_message = user_response


def _display_qa_result(result_data: dict) -> None:
    """Display a QA audit result with colored output."""
    click.echo()
    click.echo(click.style(result_data.get("summary", ""), bold=True))

    violations = result_data.get("violations", [])
    if violations:
        click.echo()
        for i, v in enumerate(violations, 1):
            fixed = v.get("fixed", False)
            needs_human = v.get("needs_human_decision", False)
            if fixed:
                icon = click.style("FIXED", fg="green")
            elif needs_human:
                icon = click.style("HUMAN?", fg="yellow")
            else:
                icon = click.style("OPEN", fg="red")
            sev = click.style(v["severity"], fg="red" if v["severity"] == "error" else "yellow")
            loc = f"{v['file']}:{v.get('line', '?')}"
            click.echo(f"  {i}. [{icon}] {sev}: {loc} — {v['message']}")

            if needs_human and v.get("human_question"):
                click.echo(click.style(f"         ↳ {v['human_question']}", dim=True))
            if fixed and v.get("fix_description"):
                click.echo(click.style(f"         ↳ {v['fix_description']}", dim=True))

    tests = result_data.get("tests_passed")
    if tests is not None:
        status = click.style("PASSED", fg="green") if tests else click.style("FAILED", fg="red")
        click.echo(f"\nTests: {status}")


async def ping_backend(base_url: str, timeout: float, raw: bool) -> int:
    """Direct health endpoint ping (no agent)."""
    import httpx

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        headers={"X-Frontend-ID": "chat"},
    ) as client:
        try:
            response = await client.get("/health/ready")
        except httpx.ConnectError:
            click.echo(click.style("Error: Backend is not reachable.", fg="red"), err=True)
            return 1

    if raw:
        click.echo(json.dumps(response.json(), indent=2))
        return 0

    if response.status_code == 200:
        data = response.json()
        checks = data.get("checks", {})
        click.echo(click.style("healthy", fg="green"))
        for comp, check in checks.items():
            status = check.get("status", "unknown")
            latency = check.get("latency_ms")
            detail = f" ({latency}ms)" if latency else ""
            color = "green" if status == "healthy" else "red" if status == "unhealthy" else "yellow"
            click.echo(f"  {click.style('●', fg=color)} {comp}: {status}{detail}")
        return 0

    if response.status_code == 503:
        data = response.json()
        checks = data.get("detail", {}).get("checks", {})
        click.echo(click.style("degraded", fg="yellow"))
        for comp, check in checks.items():
            status = check.get("status", "unknown")
            color = "green" if status == "healthy" else "red" if status == "unhealthy" else "yellow"
            click.echo(f"  {click.style('●', fg=color)} {comp}: {status}")
        return 1

    click.echo(click.style(f"Backend returned {response.status_code}", fg="yellow"), err=True)
    return 1


async def list_agents_cmd(base_url: str, timeout: float, raw: bool) -> int:
    """List all available agents from the registry."""
    import httpx

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        headers={"X-Frontend-ID": "chat"},
    ) as client:
        try:
            response = await client.get("/api/v1/agents/registry")
        except httpx.ConnectError:
            click.echo(click.style("Error: Backend is not reachable.", fg="red"), err=True)
            return 1

    if raw:
        click.echo(json.dumps(response.json(), indent=2))
        return 0

    if response.status_code != 200:
        click.echo(click.style(f"Error: {response.text}", fg="red"), err=True)
        return 1

    agents = response.json().get("data", [])
    if not agents:
        click.echo("No agents registered.")
        return 0

    for agent in agents:
        name = agent["agent_name"]
        desc = agent.get("description", "")
        keywords = ", ".join(agent.get("keywords", []))
        tools = ", ".join(agent.get("tools", []))
        click.echo(f"  {click.style(name, fg='cyan', bold=True)}  {desc}")
        if keywords:
            click.echo(f"    keywords: {keywords}")
        if tools:
            click.echo(f"    tools: {tools}")

    return 0


@click.command()
@click.option("--message", "-m", default=None, help="Message to send to the agent.")
@click.option("--agent", "-a", default=None, help="Target a specific agent by name (bypass routing).")
@click.option("--list-agents", is_flag=True, help="List all available agents.")
@click.option("--ping", is_flag=True, help="Ping the health endpoint directly (no agent).")
@click.option("--raw", is_flag=True, help="Output raw JSON response.")
@click.option("--verbose", "-v", is_flag=True, help="Show agent name, components, and advice.")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging.")
@click.option("--port", default=None, type=int, help="Backend server port (overrides config).")
def main(message: str | None, agent: str | None, list_agents: bool, ping: bool, raw: bool, verbose: bool, debug: bool, port: int | None) -> None:
    """
    Send a message to platform agents.

    Examples:

        python chat.py --list-agents

        python chat.py --message "check system health"

        python chat.py --message "check system health" --verbose

        python chat.py --agent system.health.agent --message "full diagnostic"

        python chat.py --message "check system health" --raw

        python chat.py --ping

        python chat.py -a system.health.agent -m "what needs fixing?" -v
    """
    validate_project_root()

    if debug:
        setup_logging(level="DEBUG", format_type="console")
    elif verbose:
        setup_logging(level="INFO", format_type="console")
    else:
        setup_logging(level="WARNING", format_type="console")

    bind_context(source="cli")

    if not message and not ping and not list_agents:
        click.echo("Error: provide --message, --ping, or --list-agents.", err=True)
        click.echo("Run 'python chat.py --help' for usage.", err=True)
        sys.exit(1)

    try:
        base_url, timeout = get_server_base_url()
        if port:
            from modules.backend.core.config import get_app_config
            host = get_app_config().application.server.host
            base_url = f"http://{host}:{port}"
    except Exception as e:
        click.echo(click.style(f"Error loading config: {e}", fg="red"), err=True)
        sys.exit(1)

    if list_agents:
        exit_code = asyncio.run(list_agents_cmd(base_url, timeout, raw))
    elif ping:
        exit_code = asyncio.run(ping_backend(base_url, timeout, raw))
    elif agent:
        exit_code = asyncio.run(send_message_stream(base_url, message, agent, raw, verbose))
    else:
        exit_code = asyncio.run(send_message(base_url, timeout, message, agent, raw, verbose))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
