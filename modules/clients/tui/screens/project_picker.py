"""Project picker modal — create or select a project on launch.

Shown when the TUI starts without a pre-selected project,
or when the user presses Ctrl+P.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from modules.clients.tui.messages import ProjectCreated, ProjectSelected


class ProjectItem(Static):
    """A clickable project row."""

    DEFAULT_CSS = """
    ProjectItem {
        height: 3;
        padding: 0 1;
    }
    ProjectItem:hover {
        background: $primary-background;
    }
    """

    def __init__(
        self, project_id: str, project_name: str, description: str, **kwargs: object
    ) -> None:
        super().__init__(**kwargs)
        self.project_id = project_id
        self.project_name = project_name
        self.description = description

    def compose(self) -> ComposeResult:
        yield Label(
            f"[bold]{self.project_name}[/bold]  [dim]{self.description[:50]}[/dim]",
            markup=True,
        )

    def on_click(self) -> None:
        self.post_message(
            ProjectSelected(
                project_id=self.project_id,
                project_name=self.project_name,
            )
        )


class ProjectPickerScreen(ModalScreen[None]):
    """Modal screen for project selection or creation."""

    DEFAULT_CSS = """
    ProjectPickerScreen {
        align: center middle;
    }
    #picker-dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #picker-dialog Label {
        margin: 0 0 1 0;
    }
    #project-list {
        max-height: 12;
    }
    #new-project-section {
        margin-top: 1;
        border-top: solid $surface-lighten-2;
        padding-top: 1;
    }
    #new-project-section Input {
        margin: 0 0 1 0;
    }
    """

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(
        self, projects: list[dict[str, str]], **kwargs: object
    ) -> None:
        super().__init__(**kwargs)
        self._projects = projects

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-dialog"):
            yield Label("[bold]Select Project[/bold]", markup=True)

            with VerticalScroll(id="project-list"):
                for proj in self._projects:
                    yield ProjectItem(
                        project_id=proj["id"],
                        project_name=proj["name"],
                        description=proj.get("description", ""),
                    )

            with Vertical(id="new-project-section"):
                yield Label("[bold]— or create new —[/bold]", markup=True)
                yield Input(
                    placeholder="Project name",
                    id="new-project-name",
                )
                yield Input(
                    placeholder="Description",
                    id="new-project-desc",
                )
                yield Button("Create", id="create-project-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create-project-btn":
            name_input = self.query_one("#new-project-name", Input)
            desc_input = self.query_one("#new-project-desc", Input)
            name = name_input.value.strip()
            desc = desc_input.value.strip()
            if name:
                self.post_message(ProjectCreated(project_name=name, description=desc))
                self.dismiss()

    def on_project_selected(self, event: ProjectSelected) -> None:
        """Bubble up and dismiss."""
        self.dismiss()
