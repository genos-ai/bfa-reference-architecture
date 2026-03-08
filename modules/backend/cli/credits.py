"""
CLI handler for --service credits.

Thin renderer over core/preflight. Checks that all models in a roster
have available credits by pinging each with a one-token call.
"""

import asyncio
import sys

import click


def check_credits(logger, roster: str = "default") -> None:
    """Verify all roster models have available credits."""
    asyncio.run(_check_credits_async(logger, roster))


async def _check_credits_async(logger, roster: str) -> None:
    from modules.backend.agents.preflight import preflight_check
    from modules.backend.cli.report import get_console, build_table

    console = get_console()
    console.print(f"Preflight credit check (roster: {roster})...\n")

    try:
        result = await preflight_check(roster_name=roster)
    except (FileNotFoundError, Exception) as e:
        console.print(f"[red]FAIL  {e}[/red]")
        sys.exit(1)

    table = build_table("Credit Check", columns=[
        ("Status", {"width": 8}),
        ("Model",  {"style": "cyan", "width": 44}),
        ("Detail", {"ratio": 1}),
    ])

    for check in result.checks:
        if check.ok:
            table.add_row(
                "[green]PASS[/green]",
                check.model_name,
                f"{check.elapsed_ms:.0f}ms",
            )
        else:
            detail = (
                "Insufficient credits — top up at console.anthropic.com"
                if check.error_type == "insufficient_credits"
                else check.error
            )
            table.add_row("[red]FAIL[/red]", check.model_name, detail)

    console.print(table)

    if result.ok:
        console.print("[green]All models OK — ready to run missions and playbooks.[/green]")
    else:
        failed = ", ".join(c.model_name for c in result.failed)
        console.print(f"[red]Preflight failed for: {failed}[/red]")
        sys.exit(1)
