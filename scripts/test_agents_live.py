#!/usr/bin/env python3
"""
Live Agent Test — exercises QA, Planning, and Verification agents against the real codebase.

Calls real LLM APIs (Anthropic). No database, no Redis, no Docker required.
Uses the same wiring that Mission Control uses — config, deps, prompts, tools.

Usage:
    python scripts/test_agents_live.py --verbose
    python scripts/test_agents_live.py --agent qa
    python scripts/test_agents_live.py --agent planning
    python scripts/test_agents_live.py --agent verification
    python scripts/test_agents_live.py --agent all
    python scripts/test_agents_live.py --debug
"""

import asyncio
import json
import sys
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger, setup_logging


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# QA Agent — read-only audit of the codebase
# ---------------------------------------------------------------------------

async def run_qa_agent() -> dict:
    """Run the QA agent against the real codebase. Returns QaAuditResult dict."""
    from pydantic_ai import UsageLimits

    from modules.backend.agents.deps.base import FileScope, QaAgentDeps
    from modules.backend.agents.mission_control.helpers import _build_model
    from modules.backend.agents.mission_control.registry import get_registry
    from modules.backend.agents.vertical.code.qa.agent import create_agent, run_agent

    logger.info("=== QA Agent: starting live audit ===")

    registry = get_registry()
    qa_config = registry.get("code.qa.agent")

    scope = FileScope(
        read_paths=qa_config.scope.read,
        write_paths=qa_config.scope.write,
    )

    deps = QaAgentDeps(
        project_root=find_project_root(),
        scope=scope,
        config=qa_config,
        on_progress=lambda event: logger.info(
            "QA progress", extra={"event": event},
        ),
    )

    model = _build_model(qa_config.model)
    agent = create_agent(model)

    result = await run_agent(
        user_message="Audit the codebase for compliance violations.",
        deps=deps,
        agent=agent,
        usage_limits=UsageLimits(request_limit=20),
    )

    result_dict = result.model_dump()

    logger.info(
        "=== QA Agent: audit complete ===",
        extra={
            "total_violations": result.total_violations,
            "errors": result.error_count,
            "warnings": result.warning_count,
            "files_scanned": result.scanned_files_count,
        },
    )

    return result_dict


# ---------------------------------------------------------------------------
# Planning Agent — decompose a QA audit mission into a task plan
# ---------------------------------------------------------------------------

async def run_planning_agent() -> dict:
    """Run the Planning Agent with a test mission brief. Returns TaskPlan dict."""
    from modules.backend.agents.deps.base import FileScope
    from modules.backend.agents.horizontal.planning.agent import (
        PlanningAgentDeps,
        create_agent,
        run_agent,
    )
    from modules.backend.agents.mission_control.helpers import _build_roster_prompt
    from modules.backend.agents.mission_control.roster import load_roster

    logger.info("=== Planning Agent: starting task decomposition ===")

    roster = load_roster("default")
    roster_prompt = _build_roster_prompt(roster)

    mission_brief = (
        "Audit the BFA reference architecture codebase for compliance violations. "
        "The codebase follows strict rules: no hardcoded values, absolute imports only, "
        "centralized logging via get_logger(), UTC datetimes via utc_now(), "
        "and files must not exceed 1000 lines. "
        "Scan all Python files under modules/ and config/. "
        "Produce a structured report of all violations with severity ratings."
    )

    config = {"model": "anthropic:claude-opus-4-20250514"}
    agent = create_agent(config)

    deps = PlanningAgentDeps(
        project_root=find_project_root(),
        scope=FileScope(read_paths=[], write_paths=[]),
        mission_brief=mission_brief,
        roster_description=roster_prompt,
        upstream_context=None,
    )

    prompt = (
        f"## Mission Brief\n\n{mission_brief}\n\n"
        f"{roster_prompt}\n\n"
        "## Output Format\n\n"
        "Return your task plan as JSON within <task_plan> tags.\n"
        "Follow the TaskPlan schema exactly.\n"
    )

    result = await run_agent(agent, deps, prompt)

    logger.info(
        "=== Planning Agent: task plan generated ===",
        extra={
            "task_count": len(result["task_plan"].get("tasks", [])),
            "has_thinking": result["thinking_trace"] is not None,
        },
    )

    return result


# ---------------------------------------------------------------------------
# Verification Agent — evaluate QA agent output
# ---------------------------------------------------------------------------

async def run_verification_agent(qa_output: dict) -> dict:
    """Run the Verification Agent against QA agent output. Returns evaluation dict."""
    from pydantic_ai import UsageLimits

    from modules.backend.agents.deps.base import BaseAgentDeps, FileScope
    from modules.backend.agents.horizontal.verification.agent import (
        create_agent,
        run_agent,
    )
    from modules.backend.agents.mission_control.helpers import _build_model

    logger.info("=== Verification Agent: evaluating QA output ===")

    model = _build_model("anthropic:claude-opus-4-20250514")
    agent = create_agent(model)

    deps = BaseAgentDeps(
        project_root=find_project_root(),
        scope=FileScope(read_paths=[], write_paths=[]),
    )

    evaluation_prompt = (
        "## Task Instructions\n\n"
        "The QA compliance agent was asked to audit the codebase for compliance "
        "violations. It should scan Python files for: hardcoded values, relative "
        "imports, direct logging imports, datetime.now() usage, os.getenv() fallbacks, "
        "and file size limits.\n\n"
        "## Evaluation Criteria\n\n"
        "1. **Completeness**: Did the agent scan all relevant rule categories?\n"
        "2. **Accuracy**: Are the reported violations real (correct file, line, rule)?\n"
        "3. **Severity classification**: Are errors and warnings correctly classified?\n"
        "4. **Actionability**: Does each violation include enough context to fix it?\n"
        "5. **No false positives**: Did the agent avoid flagging compliant code?\n\n"
        "## Agent Output\n\n"
        f"```json\n{json.dumps(qa_output, indent=2)}\n```\n"
    )

    result = await run_agent(
        user_message=evaluation_prompt,
        deps=deps,
        agent=agent,
        usage_limits=UsageLimits(request_limit=5),
    )

    result_dict = result.model_dump()

    logger.info(
        "=== Verification Agent: evaluation complete ===",
        extra={
            "overall_score": result.overall_score,
            "passed": result.passed,
            "blocking_issues": len(result.blocking_issues),
        },
    )

    return result_dict


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_qa_results(result: dict) -> None:
    """Print QA audit results in a readable format."""
    click.echo(click.style("\n" + "=" * 70, fg="cyan"))
    click.echo(click.style("  QA AUDIT RESULTS", fg="cyan", bold=True))
    click.echo(click.style("=" * 70, fg="cyan"))

    click.echo(f"\nSummary: {result['summary']}")
    click.echo(f"Files scanned: {result['scanned_files_count']}")
    click.echo(
        f"Violations: {result['total_violations']} "
        f"({result['error_count']} errors, {result['warning_count']} warnings)"
    )

    if result["violations"]:
        click.echo(click.style("\nViolations:", bold=True))
        for v in result["violations"]:
            severity_color = "red" if v["severity"] == "error" else "yellow"
            loc = f"{v['file']}:{v['line']}" if v.get("line") else v["file"]
            click.echo(
                f"  {click.style(v['severity'].upper(), fg=severity_color):>12s}  "
                f"{v['rule_id']:30s}  {loc}"
            )
            click.echo(f"{'':>14s}{v['message']}")
            if v.get("recommendation"):
                click.echo(
                    f"{'':>14s}{click.style('→ ' + v['recommendation'], fg='green')}"
                )


def print_planning_results(result: dict) -> None:
    """Print Planning Agent results in a readable format."""
    click.echo(click.style("\n" + "=" * 70, fg="cyan"))
    click.echo(click.style("  PLANNING AGENT RESULTS", fg="cyan", bold=True))
    click.echo(click.style("=" * 70, fg="cyan"))

    plan = result["task_plan"]
    tasks = plan.get("tasks", [])
    click.echo(f"\nTasks: {len(tasks)}")

    for task in tasks:
        click.echo(f"\n  Task: {task.get('task_id', 'unknown')}")
        click.echo(f"    Agent: {task.get('agent_name', 'unknown')}")
        click.echo(f"    Description: {task.get('instructions', 'none')[:120]}")
        deps = task.get("dependencies", [])
        if deps:
            click.echo(f"    Depends on: {', '.join(deps)}")

    if result.get("thinking_trace"):
        click.echo(click.style("\nThinking trace captured (truncated):", dim=True))
        click.echo(f"  {result['thinking_trace'][:300]}...")


def print_verification_results(result: dict) -> None:
    """Print Verification Agent results in a readable format."""
    click.echo(click.style("\n" + "=" * 70, fg="cyan"))
    click.echo(click.style("  VERIFICATION RESULTS", fg="cyan", bold=True))
    click.echo(click.style("=" * 70, fg="cyan"))

    score = result["overall_score"]
    passed = result["passed"]
    status_color = "green" if passed else "red"
    status_text = "PASSED" if passed else "FAILED"

    click.echo(f"\nOverall score: {score:.2f}")
    click.echo(f"Status: {click.style(status_text, fg=status_color, bold=True)}")

    if result.get("criteria_results"):
        click.echo(click.style("\nCriteria:", bold=True))
        for cr in result["criteria_results"]:
            cr_color = "green" if cr["passed"] else "red"
            click.echo(
                f"  {click.style('✓' if cr['passed'] else '✗', fg=cr_color)} "
                f"{cr['criterion']} — {cr['score']:.2f}"
            )
            if cr.get("issues"):
                for issue in cr["issues"]:
                    click.echo(f"      {click.style('⚠ ' + issue, fg='yellow')}")

    if result.get("blocking_issues"):
        click.echo(click.style("\nBlocking issues:", fg="red", bold=True))
        for issue in result["blocking_issues"]:
            click.echo(f"  ✗ {issue}")

    if result.get("recommendations"):
        click.echo(click.style("\nRecommendations:", bold=True))
        for rec in result["recommendations"]:
            click.echo(f"  → {rec}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.option("--debug", "-d", is_flag=True, help="Enable debug output.")
@click.option(
    "--agent", "-a",
    type=click.Choice(["qa", "planning", "verification", "all"]),
    default="all",
    help="Which agent(s) to run.",
)
def main(verbose: bool, debug: bool, agent: str) -> None:
    """Run live agent tests against the real codebase with real LLM calls."""
    if debug:
        setup_logging(level="DEBUG", format_type="console")
    elif verbose:
        setup_logging(level="INFO", format_type="console")
    else:
        setup_logging(level="WARNING", format_type="console")

    async def _run():
        qa_output = None

        if agent in ("qa", "all"):
            qa_output = await run_qa_agent()
            print_qa_results(qa_output)

        if agent in ("planning", "all"):
            planning_output = await run_planning_agent()
            print_planning_results(planning_output)

        if agent in ("verification", "all"):
            if qa_output is None:
                click.echo("Running QA agent first to get output for verification...")
                qa_output = await run_qa_agent()
                print_qa_results(qa_output)

            verification_output = await run_verification_agent(qa_output)
            print_verification_results(verification_output)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
