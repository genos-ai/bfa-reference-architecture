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

    click.echo(f"Preflight credit check (roster: {roster})...\n")

    try:
        result = await preflight_check(roster_name=roster)
    except FileNotFoundError as e:
        click.echo(click.style(f"✗ FAIL  {e}", fg="red"))
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ FAIL  {e}", fg="red"))
        sys.exit(1)

    for check in result.checks:
        if check.ok:
            click.echo(
                click.style("✓ PASS", fg="green")
                + f"  {check.model_name} ({check.elapsed_ms:.0f}ms)"
            )
        else:
            click.echo(
                click.style("✗ FAIL", fg="red")
                + f"  {check.model_name}"
            )
            if check.error_type == "insufficient_credits":
                click.echo("         Insufficient credits — top up at: https://console.anthropic.com/settings/billing")
            else:
                click.echo(f"         {check.error}")

    click.echo()
    if result.ok:
        click.echo(click.style("All models OK — ready to run missions and playbooks.", fg="green"))
    else:
        failed = ", ".join(c.model_name for c in result.failed)
        click.echo(click.style(f"Preflight failed for: {failed}", fg="red"))
        sys.exit(1)
