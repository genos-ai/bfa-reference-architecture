"""
CLI handler for context inspection commands.

Shows what agents actually see: Code Map, PQI scores, dependency analysis,
and the assembled context layers.

Two modes:
  - Global (no --project): reads Code Map / PQI from disk. No DB needed.
  - Per-project (--project <id>): builds the full assembled context packet
    (PCD + Code Map + history) via ContextAssembler. Requires DB.
"""

import asyncio
import json as _json
import sys
from pathlib import Path

from modules.clients.cli.report import get_console, build_table
from modules.backend.core.config import find_project_root
from modules.backend.core.utils import estimate_tokens


def run_context(cli_logger, action: str, *, output_format: str = "human", **kwargs) -> None:
    """Dispatch context CLI actions."""
    actions = {
        "show": _action_show,
        "assembled": _action_assembled,
        "codemap": _action_codemap,
        "pqi": _action_pqi,
        "deps": _action_deps,
    }
    fn = actions.get(action)
    if not fn:
        get_console().print(f"[red]Unknown action: {action}[/red]")
        sys.exit(1)

    fn(cli_logger, output_format=output_format, **kwargs)


# ---------------------------------------------------------------------------
# context show — full assembled context overview
# ---------------------------------------------------------------------------


def _action_show(cli_logger, *, output_format, project_id=None, **_):
    """Show all context layers and their token costs.

    Without --project: global (disk-only, no DB).
    With --project: includes PCD and history from DB.
    """
    console = get_console()
    project_root = find_project_root()

    # If project_id given, delegate to assembled view
    if project_id:
        _action_assembled(cli_logger, output_format=output_format, project_id=project_id)
        return

    from modules.backend.services.code_map.loader import CodeMapLoader

    loader = CodeMapLoader(project_root)

    # Layer 3: Code Map
    code_map_json = loader.get_json()
    code_map_md = loader.get_markdown()
    is_stale = loader.is_stale()

    console.print("[bold]Context Layers (what agents receive)[/bold]\n")

    # Code Map status
    if code_map_json:
        stats = code_map_json.get("stats", {})
        commit = code_map_json.get("commit", "")[:12]
        stale_tag = " [yellow](STALE)[/yellow]" if is_stale else " [green](fresh)[/green]"

        json_tokens = estimate_tokens(code_map_json)
        md_tokens = estimate_tokens(code_map_md) if code_map_md else 0

        console.print(f"[bold cyan]Layer 3: Code Map[/bold cyan]{stale_tag}")
        console.print(f"  Commit:    {commit}")
        console.print(f"  Files:     {stats.get('total_files', 0)}")
        console.print(f"  Lines:     {stats.get('total_lines', 0):,}")
        console.print(f"  Classes:   {stats.get('total_classes', 0)}")
        console.print(f"  Functions: {stats.get('total_functions', 0)}")
        console.print(f"  JSON:      ~{json_tokens:,} tokens")
        console.print(f"  Markdown:  ~{md_tokens:,} tokens")
    else:
        console.print("[bold cyan]Layer 3: Code Map[/bold cyan] [red](missing)[/red]")
        console.print("  Run: python cli.py context codemap --generate")

    # PQI score
    console.print()
    try:
        from modules.backend.services.pqi.scorer import score_project

        result = score_project(
            repo_root=project_root,
            scope=["modules/"],
            code_map=code_map_json,
        )
        band_colors = {
            "excellent": "green", "good": "cyan",
            "fair": "yellow", "poor": "red",
        }
        color = band_colors.get(result.quality_band.value, "white")
        console.print(
            f"[bold cyan]PQI Score[/bold cyan]  "
            f"[{color}]{result.composite:.1f}/100 ({result.quality_band.value})[/{color}]"
        )
        for name, dim in result.dimensions.items():
            bar_len = int(dim.score / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            console.print(f"  {name:<16s} {bar} {dim.score:.1f}")
    except Exception as exc:
        console.print(f"[bold cyan]PQI Score[/bold cyan] [red](unavailable: {exc})[/red]")

    # Dependency analysis
    console.print()
    if code_map_json:
        from modules.backend.services.code_map.assembler import find_circular_deps

        import_graph = code_map_json.get("import_graph", {})
        cycles = find_circular_deps(import_graph)
        total_edges = sum(len(deps) for deps in import_graph.values())

        console.print(f"[bold cyan]Dependency Graph[/bold cyan]")
        console.print(f"  Modules: {len(import_graph)}")
        console.print(f"  Edges:   {total_edges}")
        if cycles:
            console.print(f"  Cycles:  [yellow]{len(cycles)}[/yellow]")
            for cycle in cycles:
                console.print(f"    [yellow]{'  →  '.join(cycle)}[/yellow]")
        else:
            console.print(f"  Cycles:  [green]0[/green]")

    # Token budget summary
    console.print()
    console.print("[bold]Token Budget (default: 12,000)[/bold]")
    if code_map_md:
        md_tokens = estimate_tokens(code_map_md)
        remaining = 12_000 - md_tokens
        console.print(f"  Code Map Markdown: ~{md_tokens:,} tokens")
        console.print(f"  Remaining for PCD + task + history: ~{remaining:,} tokens")


# ---------------------------------------------------------------------------
# context assembled — full per-project context packet (requires DB)
# ---------------------------------------------------------------------------


def _action_assembled(cli_logger, *, output_format, project_id=None, domain_tags=None, **_):
    """Build and display the full assembled context packet for a project.

    This is exactly what an agent receives before task execution:
    PCD (Layer 0), task stub (Layer 1), Code Map (Layer 3), history (Layer 2).
    """
    console = get_console()

    if not project_id:
        console.print("[red]--project is required for assembled context[/red]")
        sys.exit(1)

    asyncio.run(_assembled_async(console, project_id, domain_tags, output_format))


async def _assembled_async(console, project_id, domain_tags, output_format):
    """Async implementation — builds the real context packet."""
    from modules.backend.services.code_map.loader import CodeMapLoader
    from modules.backend.services.context_assembler import ContextAssembler
    from modules.backend.services.history_query import HistoryQueryService
    from modules.backend.services.project_context import ProjectContextManager

    project_root = find_project_root()

    async with ProjectContextManager.factory() as pcd_manager:
        async with HistoryQueryService.factory() as history_service:
            code_map_loader = CodeMapLoader(project_root)

            assembler = ContextAssembler(
                context_manager=pcd_manager,
                history_service=history_service,
                code_map_loader=code_map_loader,
            )

            # Use a synthetic task definition to show what the assembler produces
            task_stub = {
                "task_id": "(preview)",
                "agent_name": "(preview)",
                "instructions": "Context preview — no real task",
            }

            tags = domain_tags or ["code", "implementation"]

            try:
                packet = await assembler.build(
                    project_id=project_id,
                    task_definition=task_stub,
                    resolved_inputs={},
                    domain_tags=tags,
                )
            except Exception as exc:
                # History query may fail if DB schema is behind — degrade gracefully
                console.print(f"[yellow]Warning: history query failed ({type(exc).__name__}), showing without history[/yellow]\n")
                packet = await assembler.build(
                    project_id=project_id,
                    task_definition=task_stub,
                    resolved_inputs={},
                    domain_tags=[],  # empty tags skip history
                )

    if output_format == "json":
        console.print_json(_json.dumps(packet, indent=2, default=str))
        return

    console.print(f"[bold]Assembled Context for project [cyan]{project_id}[/cyan][/bold]")
    console.print(f"  Domain tags: {tags}\n")

    # Layer 0: PCD
    pcd = packet.get("project_context")
    if pcd:
        pcd_tokens = estimate_tokens(pcd)
        console.print(f"[bold cyan]Layer 0: Project Context Document (PCD)[/bold cyan]  ~{pcd_tokens:,} tokens")
        # Show top-level keys
        if isinstance(pcd, dict):
            for key in pcd:
                val = pcd[key]
                if isinstance(val, str) and len(val) > 80:
                    val = val[:80] + "..."
                elif isinstance(val, (dict, list)):
                    val = f"<{type(val).__name__}, {len(val)} items>"
                console.print(f"  {key}: {val}")
        console.print()
    else:
        console.print("[bold cyan]Layer 0: PCD[/bold cyan] [dim](empty — no PCD for this project)[/dim]\n")

    # Layer 1: Task
    task = packet.get("task")
    if task:
        task_tokens = estimate_tokens(task)
        console.print(f"[bold cyan]Layer 1: Task Definition[/bold cyan]  ~{task_tokens:,} tokens")
        console.print(f"  (preview stub — real task injected at dispatch time)")
        console.print()

    # Layer 1: Inputs
    inputs = packet.get("inputs")
    if inputs:
        input_tokens = estimate_tokens(inputs)
        console.print(f"[bold cyan]Layer 1: Resolved Inputs[/bold cyan]  ~{input_tokens:,} tokens")
        if isinstance(inputs, dict):
            for key in inputs:
                console.print(f"  {key}: {inputs[key]}")
        console.print()

    # Layer 3: Code Map
    code_map = packet.get("code_map")
    if code_map:
        cm_tokens = estimate_tokens(code_map)
        lines = code_map.count("\n") if isinstance(code_map, str) else 0
        console.print(f"[bold cyan]Layer 3: Code Map Markdown[/bold cyan]  ~{cm_tokens:,} tokens ({lines} lines)")
        # Show first 5 lines as preview
        if isinstance(code_map, str):
            preview = "\n".join(code_map.split("\n")[:5])
            console.print(f"  [dim]{preview}[/dim]")
        console.print()
    else:
        console.print("[bold cyan]Layer 3: Code Map[/bold cyan] [dim](not included for these domain tags)[/dim]\n")

    # Layer 2: History
    history = packet.get("history")
    if history:
        hist_tokens = estimate_tokens(history)
        console.print(f"[bold cyan]Layer 2: Project History[/bold cyan]  ~{hist_tokens:,} tokens")
        failures = history.get("recent_failures", [])
        executions = history.get("recent_executions", [])
        if failures:
            console.print(f"  Recent failures: {len(failures)}")
        if executions:
            console.print(f"  Recent executions: {len(executions)}")
            for ex in executions[:3]:
                agent = ex.get("agent_name", "?")
                status = ex.get("status", "?")
                console.print(f"    {agent}: {status}")
        console.print()
    else:
        console.print("[bold cyan]Layer 2: History[/bold cyan] [dim](none available)[/dim]\n")

    # Total
    total_tokens = sum(
        estimate_tokens(v) for v in packet.values() if v is not None
    )
    console.print(f"[bold]Total: ~{total_tokens:,} tokens across {len(packet)} layers[/bold]")


# ---------------------------------------------------------------------------
# context codemap — show or generate the Code Map
# ---------------------------------------------------------------------------


def _action_codemap(cli_logger, *, output_format, generate=False, format_type="markdown", **_):
    """Show or generate the Code Map."""
    console = get_console()
    project_root = find_project_root()

    from modules.backend.services.code_map.loader import CodeMapLoader

    loader = CodeMapLoader(project_root)

    if generate:
        console.print("[dim]Generating Code Map...[/dim]")
        code_map = loader.regenerate()
        if code_map is None:
            console.print("[red]Failed to generate Code Map.[/red]")
            sys.exit(1)
        stats = code_map.get("stats", {})
        console.print(
            f"[green]Code Map generated:[/green] "
            f"{stats.get('total_files', 0)} files, "
            f"{stats.get('total_lines', 0):,} lines"
        )
        console.print()

    if format_type == "json":
        code_map = loader.get_json()
        if code_map is None:
            console.print("[red]No Code Map found. Run with --generate first.[/red]")
            sys.exit(1)
        if output_format == "json":
            console.print_json(_json.dumps(code_map))
        else:
            console.print(_json.dumps(code_map, indent=2))
    else:
        md = loader.get_markdown()
        if md is None:
            console.print("[red]No Code Map found. Run with --generate first.[/red]")
            sys.exit(1)
        console.print(md)


# ---------------------------------------------------------------------------
# context pqi — run PQI scorer
# ---------------------------------------------------------------------------


def _action_pqi(cli_logger, *, output_format, **_):
    """Run the PQI scorer and display results."""
    console = get_console()
    project_root = find_project_root()

    from modules.backend.services.code_map.loader import CodeMapLoader
    from modules.backend.services.pqi.scorer import score_project

    loader = CodeMapLoader(project_root)
    code_map = loader.get_json()

    console.print("[dim]Running PyQuality Index scorer...[/dim]\n")

    result = score_project(
        repo_root=project_root,
        scope=["modules/"],
        code_map=code_map,
    )

    if output_format == "json":
        from dataclasses import asdict
        console.print_json(_json.dumps(asdict(result), default=str))
        return

    band_colors = {
        "excellent": "green", "good": "cyan",
        "fair": "yellow", "poor": "red",
    }
    color = band_colors.get(result.quality_band.value, "white")

    console.print(
        f"[bold]PyQuality Index:[/bold]  "
        f"[{color} bold]{result.composite:.1f}/100  ({result.quality_band.value.upper()})[/{color} bold]"
    )
    console.print(f"  Files:     {result.file_count}")
    console.print(f"  Lines:     {result.line_count:,}")
    if result.floor_penalty > 0:
        console.print(f"  Floor penalty: [yellow]{result.floor_penalty:.3f}[/yellow]")
    console.print()

    table = build_table("Dimensions", columns=[
        ("Dimension", {"style": "cyan", "width": 18}),
        ("Score", {"width": 8}),
        ("Confidence", {"width": 12}),
        ("Bar", {"width": 22}),
        ("Recommendations", {"ratio": 1}),
    ])

    for name, dim in result.dimensions.items():
        bar_len = int(dim.score / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)

        if dim.score >= 80:
            score_str = f"[green]{dim.score:.1f}[/green]"
        elif dim.score >= 60:
            score_str = f"[cyan]{dim.score:.1f}[/cyan]"
        elif dim.score >= 40:
            score_str = f"[yellow]{dim.score:.1f}[/yellow]"
        else:
            score_str = f"[red]{dim.score:.1f}[/red]"

        recs = "; ".join(dim.recommendations[:2]) if dim.recommendations else "—"
        table.add_row(name, score_str, f"{dim.confidence:.0%}", bar, recs)

    console.print(table)


# ---------------------------------------------------------------------------
# context deps — dependency analysis
# ---------------------------------------------------------------------------


def _action_deps(cli_logger, *, output_format, **_):
    """Show dependency graph analysis."""
    console = get_console()
    project_root = find_project_root()

    from modules.backend.services.code_map.loader import CodeMapLoader
    from modules.backend.services.code_map.assembler import find_circular_deps

    loader = CodeMapLoader(project_root)
    code_map = loader.get_json()

    if code_map is None:
        console.print("[red]No Code Map found. Run: python cli.py context codemap --generate[/red]")
        sys.exit(1)

    import_graph = code_map.get("import_graph", {})
    modules = code_map.get("modules", {})
    cycles = find_circular_deps(import_graph)
    total_edges = sum(len(deps) for deps in import_graph.values())

    if output_format == "json":
        console.print_json(_json.dumps({
            "total_modules": len(modules),
            "total_edges": total_edges,
            "circular_dependencies": [" → ".join(c) for c in cycles],
        }))
        return

    console.print(f"[bold]Dependency Graph[/bold]")
    console.print(f"  Modules: {len(import_graph)}")
    console.print(f"  Edges:   {total_edges}")
    console.print()

    # Circular deps
    if cycles:
        console.print(f"[bold yellow]Circular Dependencies ({len(cycles)}):[/bold yellow]")
        for cycle in cycles:
            console.print(f"  [yellow]{'  →  '.join(cycle)}[/yellow]")
    else:
        console.print("[green]No circular dependencies found.[/green]")

    # Top modules by PageRank
    console.print()
    ranked = sorted(
        modules.items(),
        key=lambda kv: kv[1].get("rank", 999),
    )

    table = build_table("Top Modules by PageRank", columns=[
        ("Rank", {"width": 8}),
        ("Module", {"style": "cyan", "ratio": 1}),
        ("Lines", {"width": 8}),
        ("Classes", {"width": 8}),
        ("Functions", {"width": 10}),
    ])

    for path, data in ranked[:15]:
        rank = data.get("rank", 0)
        lines = data.get("lines", 0)
        n_classes = len(data.get("classes", {}))
        n_funcs = len(data.get("functions", {}))
        table.add_row(f"{rank:.4f}", path, str(lines), str(n_classes), str(n_funcs))

    console.print(table)
