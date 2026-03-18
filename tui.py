"""
TUI Client — Mission Control Dashboard.

In-process interactive terminal interface for the agentic AI platform.
Calls backend services directly (not via HTTP) for gate integration
and real-time event streaming.

Usage:
    python tui.py
    python tui.py --verbose
    python tui.py --debug
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import click

from modules.backend.core.config import validate_project_root
from modules.backend.core.logging import bind_context, get_logger, setup_logging


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output (INFO level logging).")
@click.option("--debug", "-d", is_flag=True, help="Enable debug output (DEBUG level logging).")
def main(verbose: bool, debug: bool) -> None:
    """BFA Mission Control — Interactive Agent Dashboard."""
    validate_project_root()

    # Disable console logging — Textual owns stdout/stderr.
    # All logs go to logs/system.jsonl (configured in logging.yaml).
    if debug:
        setup_logging(level="DEBUG", enable_console=False)
    elif verbose:
        setup_logging(level="INFO", enable_console=False)
    else:
        setup_logging(level="WARNING", enable_console=False)

    bind_context(source="tui")

    logger = get_logger(__name__)
    logger.debug("Starting Mission Control TUI", extra={"debug": debug, "verbose": verbose})

    from modules.clients.tui import BfaTuiApp

    app = BfaTuiApp()
    app.run()


if __name__ == "__main__":
    main()
