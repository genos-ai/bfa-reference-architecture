#!/usr/bin/env python3
"""
Live Agent Test — exercises agents and the full dispatch pipeline against the real codebase.

Calls real LLM APIs (Anthropic). No database, no Redis, no Docker required.
Uses the same wiring that Mission Control uses — config, deps, prompts, tools.

Usage:
    python scripts/test_agents_live.py --verbose
    python scripts/test_agents_live.py --agent qa
    python scripts/test_agents_live.py --agent health
    python scripts/test_agents_live.py --agent planning
    python scripts/test_agents_live.py --agent verification
    python scripts/test_agents_live.py --agent mission
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
    from modules.backend.agents.vertical.code.quality.agent import create_agent, run_agent

    logger.info("=== QA Agent: starting live audit ===")

    registry = get_registry()
    qa_config = registry.get("code.quality.agent")

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
# Health Agent — read-only platform health audit
# ---------------------------------------------------------------------------

async def run_health_agent() -> dict:
    """Run the Health agent against the real codebase. Returns HealthCheckResult dict."""
    from pydantic_ai import UsageLimits

    from modules.backend.agents.deps.base import FileScope, HealthAgentDeps
    from modules.backend.agents.mission_control.helpers import _build_model
    from modules.backend.agents.mission_control.registry import get_registry
    from modules.backend.agents.vertical.system.health.agent import create_agent, run_agent
    from modules.backend.core.config import get_app_config

    logger.info("=== Health Agent: starting platform health audit ===")

    registry = get_registry()
    health_config = registry.get("system.health.agent")

    scope = FileScope(
        read_paths=health_config.scope.read,
        write_paths=health_config.scope.write,
    )

    deps = HealthAgentDeps(
        project_root=find_project_root(),
        scope=scope,
        config=health_config,
        app_config=get_app_config(),
    )

    model = _build_model(health_config.model)
    agent = create_agent(model)

    result = await run_agent(
        user_message="Run a full platform health audit. Check logs, config, dependencies, and file structure.",
        deps=deps,
        agent=agent,
        usage_limits=UsageLimits(request_limit=15),
    )

    result_dict = result.model_dump()

    logger.info(
        "=== Health Agent: audit complete ===",
        extra={
            "overall_status": result.overall_status,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "checks": result.checks_performed,
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


def print_health_results(result: dict) -> None:
    """Print Health Agent results in a readable format."""
    click.echo(click.style("\n" + "=" * 70, fg="cyan"))
    click.echo(click.style("  HEALTH AUDIT RESULTS", fg="cyan", bold=True))
    click.echo(click.style("=" * 70, fg="cyan"))

    status = result["overall_status"]
    status_color = {"healthy": "green", "degraded": "yellow", "unhealthy": "red"}.get(
        status, "white"
    )

    click.echo(f"\nSummary: {result['summary']}")
    click.echo(f"Status: {click.style(status.upper(), fg=status_color, bold=True)}")
    click.echo(
        f"Issues: {result['error_count']} errors, {result['warning_count']} warnings"
    )
    click.echo(f"Checks performed: {', '.join(result['checks_performed'])}")

    if result["findings"]:
        click.echo(click.style("\nFindings:", bold=True))
        for f in result["findings"]:
            severity_color = {
                "error": "red", "warning": "yellow", "info": "blue",
            }.get(f["severity"], "white")
            click.echo(
                f"  {click.style(f['severity'].upper(), fg=severity_color):>12s}  "
                f"[{f['category']}] {f['message']}"
            )
            if f.get("details"):
                click.echo(f"{'':>14s}{f['details']}")


# ---------------------------------------------------------------------------
# Full Mission — end-to-end dispatch pipeline
# ---------------------------------------------------------------------------

SELF_AUDIT_MISSION_BRIEF = (
    "Run a full platform self-audit of the BFA reference architecture. "
    "This is a read-only audit — no files should be modified (P13). "
    "The audit should cover two areas:\n\n"
    "1. **Code compliance**: Scan all Python files under modules/ and config/ "
    "for violations of project rules: no hardcoded values, absolute imports only, "
    "centralized logging via get_logger(), UTC datetimes via utc_now(), "
    "and files must not exceed 1000 lines.\n\n"
    "2. **Platform health**: Check log files for errors and warnings, "
    "validate config files and secrets, check dependency consistency, "
    "and verify project file structure.\n\n"
    "Produce structured reports from each check."
)


async def run_mission() -> dict:
    """Run the full dispatch pipeline: Planning → Validate → Dispatch → Verify."""
    from modules.backend.agents.mission_control.mission_control import handle_mission

    logger.info("=== Mission: starting full dispatch pipeline ===")

    mission_id = "live-test-self-audit"

    outcome = await handle_mission(
        mission_id=mission_id,
        mission_brief=SELF_AUDIT_MISSION_BRIEF,
        session_service=None,
        roster_name="default",
        mission_budget_usd=10.0,
    )

    outcome_dict = outcome.model_dump()

    logger.info(
        "=== Mission: dispatch complete ===",
        extra={
            "status": outcome.status,
            "total_cost_usd": outcome.total_cost_usd,
            "total_duration_seconds": outcome.total_duration_seconds,
            "task_count": len(outcome.task_results),
        },
    )

    return outcome_dict


def print_mission_results(result: dict) -> None:
    """Print MissionOutcome in a readable format."""
    click.echo(click.style("\n" + "=" * 70, fg="magenta"))
    click.echo(click.style("  MISSION OUTCOME", fg="magenta", bold=True))
    click.echo(click.style("=" * 70, fg="magenta"))

    status = result["status"]
    status_color = {
        "success": "green", "partial": "yellow", "failed": "red",
    }.get(status, "white")

    click.echo(f"\nMission ID: {result['mission_id']}")
    click.echo(f"Status: {click.style(status.upper(), fg=status_color, bold=True)}")
    click.echo(f"Duration: {result['total_duration_seconds']:.1f}s")
    click.echo(f"Total cost: ${result['total_cost_usd']:.4f}")

    tokens = result.get("total_tokens", {})
    click.echo(
        f"Tokens: {tokens.get('input', 0)} in / "
        f"{tokens.get('output', 0)} out / "
        f"{tokens.get('thinking', 0)} thinking"
    )

    if result.get("task_results"):
        click.echo(click.style("\nTask Results:", bold=True))
        for tr in result["task_results"]:
            task_status = tr["status"]
            task_color = {
                "success": "green", "failed": "red", "timeout": "yellow",
            }.get(task_status, "white")

            click.echo(
                f"\n  {click.style(task_status.upper(), fg=task_color):>12s}  "
                f"{tr['task_id']} ({tr['agent_name']})"
            )
            click.echo(f"{'':>14s}Duration: {tr['duration_seconds']:.1f}s | Cost: ${tr['cost_usd']:.4f}")

            # Verification outcome
            vo = tr.get("verification_outcome", {})
            tier_statuses = []
            for tier_name in ("tier_1", "tier_2", "tier_3"):
                tier = vo.get(tier_name, {})
                ts = tier.get("status", "skipped")
                tier_statuses.append(f"T{tier_name[-1]}:{ts}")
            click.echo(f"{'':>14s}Verification: {' | '.join(tier_statuses)}")

            # Retry history
            if tr.get("retry_history"):
                click.echo(f"{'':>14s}Retries: {tr['retry_count']}")
                for rh in tr["retry_history"]:
                    click.echo(
                        f"{'':>16s}Attempt {rh['attempt']}: "
                        f"tier {rh['failure_tier']} — {rh['failure_reason'][:80]}"
                    )

    if result.get("planning_trace_reference"):
        click.echo(click.style("\nPlanning trace captured (truncated):", dim=True))
        trace = result["planning_trace_reference"]
        click.echo(f"  {trace[:400]}..." if len(trace) > 400 else f"  {trace}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.option("--debug", "-d", is_flag=True, help="Enable debug output.")
@click.option(
    "--agent", "-a",
    type=click.Choice(["qa", "health", "planning", "verification", "mission", "all"]),
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

        if agent in ("health", "all"):
            health_output = await run_health_agent()
            print_health_results(health_output)

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

        if agent == "mission":
            mission_output = await run_mission()
            print_mission_results(mission_output)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
