"""Gate review modal — pauses dispatch for human decision.

Shows gate context (tasks, cost, verification) and lets the user
pick an action: Continue, Skip, Retry, Modify, or Abort.
Each gate type shows a tailored view with relevant context.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, TextArea

from modules.backend.agents.mission_control.gate import (
    GateAction,
    GateContext,
    GateDecision,
)
from modules.clients.common.gate_helpers import (
    ACTION_COLORS,
    cost_color,
    gate_header,
    status_icon,
)
from modules.clients.tui.messages import GateReviewCompleted


# ── Gate type display names ──────────────────────────────────────────

_GATE_TITLES: dict[str, str] = {
    "pre_dispatch": "Pre-Dispatch Review",
    "pre_layer": "Pre-Layer Review",
    "post_task": "Post-Task Review",
    "verification_failed": "Verification Failed",
    "post_layer": "Post-Layer Review",
}

# Actions available per gate type
_GATE_ACTIONS: dict[str, list[GateAction]] = {
    "pre_dispatch": [GateAction.CONTINUE, GateAction.ABORT],
    "pre_layer": [GateAction.CONTINUE, GateAction.SKIP, GateAction.ABORT],
    "post_task": [GateAction.CONTINUE, GateAction.RETRY, GateAction.SKIP, GateAction.ABORT],
    "verification_failed": [GateAction.RETRY, GateAction.MODIFY, GateAction.SKIP, GateAction.ABORT],
    "post_layer": [GateAction.CONTINUE, GateAction.ABORT],
}


def _render_context_body(ctx: GateContext) -> str:
    """Build Rich-markup body text for the gate context."""
    lines: list[str] = []
    cc = cost_color(ctx.total_cost_usd, ctx.budget_usd)

    # Cost line
    lines.append(
        f"[bold]Cost:[/bold] [{cc}]${ctx.total_cost_usd:.4f}[/{cc}]"
        f" / ${ctx.budget_usd:.2f}"
    )

    # Layer info
    if ctx.total_layers > 0:
        lines.append(
            f"[bold]Layer:[/bold] {ctx.layer_index + 1} / {ctx.total_layers}"
        )

    # Pending tasks
    if ctx.pending_tasks:
        lines.append("")
        lines.append(f"[bold]Pending Tasks ({len(ctx.pending_tasks)}):[/bold]")
        for t in ctx.pending_tasks[:10]:
            agent = t.get("agent", "?")
            desc = t.get("description", "?")[:40]
            lines.append(f"  [dim]•[/dim] [{agent}] {desc}")
        if len(ctx.pending_tasks) > 10:
            lines.append(f"  [dim]... and {len(ctx.pending_tasks) - 10} more[/dim]")

    # Task result (post_task / verification_failed)
    if ctx.task_id:
        lines.append("")
        lines.append(f"[bold]Task:[/bold] {ctx.task_id}")

    # Verification details
    if ctx.verification:
        lines.append("")
        v = ctx.verification
        lines.append("[bold]Verification:[/bold]")
        if isinstance(v, dict):
            for tier_key in ("tier_1", "tier_2", "tier_3"):
                tier = v.get(tier_key)
                if tier and isinstance(tier, dict):
                    passed = tier.get("passed", tier.get("status", "?"))
                    icon = status_icon("success" if passed else "failed")
                    lines.append(f"  {icon} {tier_key}")
                    details = tier.get("details") or tier.get("message")
                    if details:
                        lines.append(f"      [dim]{str(details)[:60]}[/dim]")

    # Completed tasks summary (pre_layer / post_layer)
    if ctx.completed_tasks:
        lines.append("")
        n = len(ctx.completed_tasks)
        lines.append(f"[bold]Completed Tasks:[/bold] {n}")

    # AI recommendation
    if ctx.ai_recommendation:
        lines.append("")
        lines.append("[bold cyan]AI Recommendation:[/bold cyan]")
        lines.append(f"  {ctx.ai_recommendation}")

    # Task output preview (post_task / verification_failed)
    if ctx.task_output:
        lines.append("")
        lines.append("[bold]Output Preview:[/bold]")
        output_str = str(ctx.task_output)[:200]
        lines.append(f"  [dim]{output_str}[/dim]")

    return "\n".join(lines)


def _action_label(action: GateAction) -> str:
    """Format an action as a labeled button string."""
    color = ACTION_COLORS.get(action.value, "white")
    shortcut = action.value[0].upper()
    return f"[{color}]{shortcut}[/{color}] {action.value.capitalize()}"


class GateReviewModal(ModalScreen[GateDecision]):
    """Modal screen for human gate review decisions."""

    DEFAULT_CSS = """
    GateReviewModal {
        align: center middle;
    }
    #gate-dialog {
        width: 80;
        height: auto;
        max-height: 85%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #gate-header {
        height: 3;
        padding: 0 1;
        background: $surface-lighten-1;
        content-align: left middle;
    }
    #gate-body-scroll {
        max-height: 20;
        margin: 1 0;
    }
    #gate-body {
        height: auto;
        padding: 0 1;
    }
    #retry-section {
        height: auto;
        margin: 1 0;
        display: none;
    }
    #retry-section.visible {
        display: block;
    }
    #retry-input {
        height: 4;
        margin: 0 0 1 0;
    }
    #gate-actions {
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    #gate-actions Button {
        margin: 0 1;
    }
    .gate-hint {
        height: 1;
        content-align: center middle;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("c", "gate_continue", "Continue", show=False),
        Binding("s", "gate_skip", "Skip", show=False),
        Binding("r", "gate_retry", "Retry", show=False),
        Binding("m", "gate_modify", "Modify", show=False),
        Binding("a", "gate_abort", "Abort", show=False),
        Binding("escape", "gate_continue", "Continue", show=False),
    ]

    def __init__(self, context: GateContext, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._gate_ctx = context
        self._available_actions = _GATE_ACTIONS.get(
            context.gate_type,
            [GateAction.CONTINUE, GateAction.ABORT],
        )

    def compose(self) -> ComposeResult:
        title = _GATE_TITLES.get(self._gate_ctx.gate_type, "Gate Review")
        header_text = gate_header(self._gate_ctx, title)

        with Vertical(id="gate-dialog"):
            yield Label(header_text, markup=True, id="gate-header")

            with VerticalScroll(id="gate-body-scroll"):
                yield Static(
                    _render_context_body(self._gate_ctx),
                    markup=True,
                    id="gate-body",
                )

            # Retry/modify instructions input (hidden by default)
            with Vertical(id="retry-section"):
                yield Label(
                    "[bold]Instructions / feedback for retry:[/bold]",
                    markup=True,
                )
                yield TextArea(id="retry-input")

            # Action buttons
            with Horizontal(id="gate-actions"):
                for action in self._available_actions:
                    color = ACTION_COLORS.get(action.value, "default")
                    variant = "error" if action == GateAction.ABORT else "default"
                    if action == GateAction.CONTINUE:
                        variant = "success"
                    yield Button(
                        action.value.capitalize(),
                        id=f"gate-btn-{action.value}",
                        variant=variant,
                    )

            # Keyboard hint
            shortcuts = "  ".join(
                f"[bold]{a.value[0]}[/bold]={a.value}"
                for a in self._available_actions
            )
            yield Label(
                f"[dim]{shortcuts}  esc=continue[/dim]",
                markup=True,
                classes="gate-hint",
            )

    # ── Action handlers ──────────────────────────────────────────────

    def _resolve(self, action: GateAction) -> None:
        """Build decision and dismiss the modal."""
        if action not in self._available_actions:
            # Fall back to continue if action isn't available for this gate type
            action = GateAction.CONTINUE

        modified_instructions: str | None = None
        if action in (GateAction.RETRY, GateAction.MODIFY):
            try:
                text_area = self.query_one("#retry-input", TextArea)
                text = text_area.text.strip()
                if text:
                    modified_instructions = text
            except NoMatches:
                pass

        decision = GateDecision(
            action=action,
            reason=f"TUI user chose {action.value}",
            modified_instructions=modified_instructions,
            reviewer="human:tui",
        )
        self.post_message(GateReviewCompleted(decision=decision))
        self.dismiss(decision)

    def action_gate_continue(self) -> None:
        self._resolve(GateAction.CONTINUE)

    def action_gate_skip(self) -> None:
        self._resolve(GateAction.SKIP)

    def action_gate_retry(self) -> None:
        # Show retry input if not visible, resolve on second press
        try:
            section = self.query_one("#retry-section")
            if "visible" not in section.classes:
                section.add_class("visible")
                self.query_one("#retry-input", TextArea).focus()
                return
        except NoMatches:
            pass
        self._resolve(GateAction.RETRY)

    def action_gate_modify(self) -> None:
        self._resolve(GateAction.MODIFY)

    def action_gate_abort(self) -> None:
        self._resolve(GateAction.ABORT)

    # ── Button handler ───────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        for action in GateAction:
            if button_id == f"gate-btn-{action.value}":
                if action == GateAction.RETRY:
                    self.action_gate_retry()
                else:
                    self._resolve(action)
                return
