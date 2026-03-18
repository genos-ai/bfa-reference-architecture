"""
CLI Interactive Gate Reviewer — Rich-based step-through for agent workflows.

Renders gate context as Rich panels and prompts the user for a decision
at each gate point. Inspect sub-commands (output, verification, inputs)
are non-consuming — they show detail and return to the prompt.

In ai_assisted mode, the AI recommendation is displayed above the prompt
so the human can see what the AI suggests before making their decision.

Usage:
    python cli.py playbook run ops.platform-audit --project my-proj --gate interactive
    python cli.py playbook run ops.platform-audit --project my-proj --gate ai_assisted
"""

import json

from rich.console import Console
from rich.panel import Panel

from modules.backend.agents.mission_control.gate import (
    GateAction,
    GateContext,
    GateDecision,
)
from modules.clients.common.display import build_table
from modules.clients.common.gate_helpers import (
    ACTION_COLORS,
    cost_color as _cost_color,
    gate_header,
    status_icon as _status_icon,
)


class CliGateReviewer:
    """Interactive CLI gate reviewer using Rich.

    Pauses at each gate point, renders context, and prompts
    the user for a decision.
    """

    def __init__(self, console: Console | None = None, verbose: bool = False):
        self.console = console or Console()
        self.verbose = verbose

    async def review(self, context: GateContext) -> GateDecision:
        handlers = {
            "pre_dispatch": self._review_pre_dispatch,
            "pre_layer": self._review_pre_layer,
            "post_task": self._review_post_task,
            "verification_failed": self._review_verification_failed,
            "post_layer": self._review_post_layer,
        }
        handler = handlers.get(context.gate_type, self._review_generic)
        return await handler(context)

    # ── Gate renderers ────────────────────────────────────────────

    async def _review_pre_dispatch(self, ctx: GateContext) -> GateDecision:
        header = self._header(ctx, "Review Task Plan")

        table = build_table(columns=[
            ("Task ID", {"style": "cyan", "width": 24}),
            ("Agent", {"width": 30}),
            ("Description", {"ratio": 1}),
        ], show_lines=True)

        for t in ctx.pending_tasks:
            table.add_row(
                t.get("task_id", "?"),
                t.get("agent", "?"),
                (t.get("description") or "")[:80],
            )

        self.console.print(Panel.fit(
            table,
            title=header,
            border_style="blue",
            padding=(1, 2),
        ))

        return self._prompt(ctx, actions="c/a/i", help_text={
            "c": "continue \u2014 execute all tasks",
            "a": "abort \u2014 cancel mission",
            "i": "inspect \u2014 show task details (JSON)",
        })

    async def _review_pre_layer(self, ctx: GateContext) -> GateDecision:
        header = self._header(ctx, f"Layer {ctx.layer_index + 1}/{ctx.total_layers}")

        table = build_table(columns=[
            ("Task ID", {"style": "cyan", "width": 24}),
            ("Agent", {"width": 30}),
            ("Input Keys", {"width": 30}),
            ("Instructions", {"ratio": 1}),
        ], show_lines=True)

        for t in ctx.pending_tasks:
            table.add_row(
                t.get("task_id", "?"),
                t.get("agent", "?"),
                ", ".join(t.get("input_keys", [])),
                (t.get("instructions") or "")[:60] + ("..." if len(t.get("instructions", "")) > 60 else ""),
            )

        self.console.print(Panel.fit(
            table,
            title=header,
            border_style="cyan",
            padding=(1, 2),
        ))

        return self._prompt(ctx, actions="c/s/a/i", help_text={
            "c": "continue \u2014 execute this layer",
            "s": "skip \u2014 skip all tasks in this layer",
            "a": "abort \u2014 cancel mission",
            "i": "inspect \u2014 show full task details",
        })

    async def _review_post_task(self, ctx: GateContext) -> GateDecision:
        header = self._header(ctx, f"Task Complete: {ctx.task_id}")

        lines = []
        if ctx.task_output:
            summary = ctx.task_output.get("summary", "")
            status = ctx.task_output.get("_meta", {})
            cost = status.get("cost_usd", 0)
            tokens_in = status.get("input_tokens", 0)
            tokens_out = status.get("output_tokens", 0)

            lines.append(f"[bold]Cost:[/bold] ${cost:.4f}  |  Tokens: {tokens_in:,} in / {tokens_out:,} out")
            if summary:
                lines.append(f"\n[bold]Summary:[/bold] {summary[:200]}")

        # Show verification tiers
        if ctx.verification:
            v = ctx.verification
            tier_strs = []
            for tier_key in ["tier_1", "tier_2", "tier_3"]:
                tier = v.get(tier_key)
                if tier:
                    status_str = _status_icon(tier.get("status", "?"))
                    tier_strs.append(f"T{tier_key[-1]} {status_str}")
            lines.append(f"\n[bold]Verification:[/bold] {' | '.join(tier_strs)}")

        # PQI if present
        pqi = ctx.task_output.get("pqi") if ctx.task_output else None
        if isinstance(pqi, dict) and pqi.get("composite"):
            lines.append(f"[bold]PQI:[/bold] {pqi['composite']:.1f}/100 ({pqi.get('quality_band', '?')})")

        body = "\n".join(lines) if lines else "[dim]No output details[/dim]"
        self.console.print(Panel(
            body,
            title=header,
            border_style="green",
            padding=(1, 2),
        ))

        return self._prompt(ctx, actions="c/r/s/a/o/v", help_text={
            "c": "continue \u2014 accept and proceed",
            "r": "retry \u2014 re-run this task",
            "s": "skip \u2014 discard result, skip task",
            "a": "abort \u2014 cancel mission",
            "o": "output \u2014 show full output (JSON)",
            "v": "verification \u2014 show verification details",
        })

    async def _review_verification_failed(self, ctx: GateContext) -> GateDecision:
        header = self._header(ctx, f"Verification FAILED: {ctx.task_id}")

        lines = ["[bold red]Verification did not pass.[/bold red]\n"]
        if ctx.verification:
            for tier_key in ["tier_1", "tier_2", "tier_3"]:
                tier = ctx.verification.get(tier_key)
                if not tier:
                    continue
                status = tier.get("status", "?")
                icon = _status_icon(status)
                details = tier.get("details", "")
                lines.append(f"  Tier {tier_key[-1]}: {icon} {status}  {details}")
                # Show failed checks for tier 2
                if tier.get("failed_checks"):
                    for check in tier["failed_checks"]:
                        lines.append(f"    [red]\u2022[/red] {check}")

        self.console.print(Panel(
            "\n".join(lines),
            title=header,
            border_style="red",
            padding=(1, 2),
        ))

        return self._prompt(ctx, actions="r/m/s/a/v", help_text={
            "r": "retry \u2014 retry with feedback (default)",
            "m": "modify \u2014 accept output despite failure",
            "s": "skip \u2014 skip this task",
            "a": "abort \u2014 cancel mission",
            "v": "verification \u2014 show full details",
        })

    async def _review_post_layer(self, ctx: GateContext) -> GateDecision:
        header = self._header(ctx, f"Layer {ctx.layer_index + 1}/{ctx.total_layers} Complete")

        # Count statuses from completed tasks in this layer
        recent = ctx.completed_tasks[-10:] if ctx.completed_tasks else []
        statuses: dict[str, int] = {}
        for t in recent:
            s = t.get("status", "?")
            statuses[s] = statuses.get(s, 0) + 1

        status_parts = [f"{_status_icon(s)} {s}: {n}" for s, n in statuses.items()]
        cost_color = _cost_color(ctx.total_cost_usd, ctx.budget_usd)

        body = (
            f"[bold]Tasks:[/bold] {' | '.join(status_parts)}\n"
            f"[bold]Cumulative cost:[/bold] [{cost_color}]${ctx.total_cost_usd:.4f}[/{cost_color}]"
            f" / ${ctx.budget_usd:.2f} budget"
        )

        self.console.print(Panel(
            body,
            title=header,
            border_style="blue",
            padding=(1, 2),
        ))

        return self._prompt(ctx, actions="c/a", help_text={
            "c": "continue \u2014 proceed to next layer",
            "a": "abort \u2014 cancel remaining layers",
        })

    async def _review_generic(self, ctx: GateContext) -> GateDecision:
        self.console.print(f"[yellow]Unknown gate type: {ctx.gate_type}[/yellow]")
        return GateDecision(action=GateAction.CONTINUE, reviewer="human")

    # ── Helpers ───────────────────────────────────────────────────

    def _header(self, ctx: GateContext, title: str) -> str:
        return gate_header(ctx, title)

    def _render_ai_recommendation(self, ctx: GateContext) -> None:
        """Render AI recommendation panel if present (ai_assisted mode)."""
        rec = ctx.ai_recommendation
        if rec is None:
            return

        # rec is a GateDecision from LlmGateReviewer
        action_str = str(rec.action.value) if hasattr(rec.action, "value") else str(rec.action)
        color = ACTION_COLORS.get(action_str, "white")

        lines = [
            f"[bold]Recommended action:[/bold] [{color}]{action_str.upper()}[/{color}]",
        ]
        if rec.reason:
            lines.append(f"[bold]Reasoning:[/bold] {rec.reason}")
        if rec.modified_instructions:
            lines.append(f"[bold]Suggested feedback:[/bold] {rec.modified_instructions}")
        lines.append(f"[dim]Reviewer: {rec.reviewer}[/dim]")

        self.console.print(Panel(
            "\n".join(lines),
            title="[bold magenta]AI Recommendation[/bold magenta]",
            border_style="magenta",
            padding=(0, 2),
        ))

    def _prompt(
        self,
        ctx: GateContext,
        actions: str,
        help_text: dict[str, str],
    ) -> GateDecision:
        """Prompt for user input. Non-consuming actions loop back."""
        # Show AI recommendation if present (ai_assisted mode)
        self._render_ai_recommendation(ctx)

        action_keys = actions.split("/")

        while True:
            self.console.print()
            prompt_parts = []
            for key in action_keys:
                desc = help_text.get(key, key)
                prompt_parts.append(f"  [bold cyan][{key}][/bold cyan] {desc}")
            self.console.print("\n".join(prompt_parts))

            choice = input("\n> ").strip().lower()
            if not choice:
                choice = action_keys[0]  # Default to first action

            if choice == "c":
                return GateDecision(action=GateAction.CONTINUE, reviewer="human")
            elif choice == "m":
                return GateDecision(action=GateAction.MODIFY, reason="Accepted despite failure", reviewer="human")
            elif choice == "a":
                reason = input("Reason (optional): ").strip() or None
                return GateDecision(action=GateAction.ABORT, reason=reason, reviewer="human")
            elif choice == "s":
                reason = input("Reason (optional): ").strip() or None
                return GateDecision(action=GateAction.SKIP, reason=reason, reviewer="human")
            elif choice == "r":
                feedback = input("Feedback for retry (optional): ").strip() or None
                return GateDecision(
                    action=GateAction.RETRY,
                    reason=feedback,
                    modified_instructions=feedback,
                    reviewer="human",
                )
            elif choice == "o":
                # Show full output JSON
                if ctx.task_output:
                    self.console.print_json(json.dumps(ctx.task_output, indent=2, default=str))
                else:
                    self.console.print("[dim]No output available[/dim]")
            elif choice == "v":
                # Show full verification details
                if ctx.verification:
                    self.console.print_json(json.dumps(ctx.verification, indent=2, default=str))
                else:
                    self.console.print("[dim]No verification data[/dim]")
            elif choice == "i":
                # Show full task details
                if ctx.pending_tasks:
                    self.console.print_json(json.dumps(ctx.pending_tasks, indent=2, default=str))
                elif ctx.current_inputs:
                    self.console.print_json(json.dumps(ctx.current_inputs, indent=2, default=str))
                else:
                    self.console.print("[dim]No detail available[/dim]")
            elif choice == "?":
                for key, desc in help_text.items():
                    self.console.print(f"  [{key}] {desc}")
            else:
                self.console.print(f"[red]Unknown action: {choice}. Try: {actions}[/red]")
