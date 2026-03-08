# 28 - CLI Architecture (Optional Module)

*Version: 2.0.0*
*Author: Architecture Team*
*Created: 2026-02-26*

## Changelog

- 2.0.0 (2026-03-08): Replaced `--options` flat model with Click groups and subcommands; AI-first discoverability (`tree`, zero-side-effect groups); Rich output for tables and panels; consolidated three scripts into one `cli.py`
- 1.0.0 (2026-02-26): Initial CLI architecture standard; extracted from 22-frontend-architecture.md (v1) and 08-python-coding-standards.md; aligned with actual codebase patterns

---

## Module Status: Optional

This module is **optional**. Adopt when your project includes command-line entry points for:
- Service lifecycle management (start, stop, restart, status)
- One-shot operations (send a message, run a health check, display config)
- Test execution and database migrations
- Scripting, automation, and CI/CD integration

**Dependencies**: This module requires **08-python-coding-standards.md** (Python conventions) and follows **03-backend-architecture.md** (API design patterns).

For interactive terminal sessions with real-time streaming, see **27-tui-architecture.md** (Textual). For web frontends, see **22-frontend-architecture.md** (React).

---

## Context

The core architecture mandates that clients are stateless presentation layers (P2) with no business logic (P1). The CLI is the simplest expression of this — a script that accepts commands, calls the backend, and displays the result.

The CLI is a single `cli.py` at the project root. It uses Click groups and subcommands to organize functionality. Every group shows help when called bare — no default actions, no side effects during exploration. An AI agent (or human) can fully understand the CLI surface in two calls: `cli.py` → `cli.py tree`.

---

## Design Rules

### AI-First Discoverability

The CLI is designed for AI agents as primary consumers. Two principles:

1. **Zero side effects during exploration.** Every group shows help when called bare. No group runs a default action. Calling `cli.py server` shows server subcommands — it does not start the server.
2. **Full surface in one call.** The `tree` command renders the entire command hierarchy with all arguments, options, and descriptions. An AI can parse this output and understand every available operation.

```bash
# First call: see top-level groups
python cli.py

# Second call: see everything
python cli.py tree
```

### Groups and Subcommands

Organize related operations into Click groups. Use subcommands for actions, arguments for targets, options for modifiers.

```bash
# Correct: groups with subcommands
python cli.py server start --port 8099 --reload
python cli.py mission run "audit the platform" --budget 2.00
python cli.py db query missions --limit 5
python cli.py migrate upgrade head

# Correct: simple commands (no subcommand needed)
python cli.py health
python cli.py credits
python cli.py agent "run a health check"
```

**Rationale**: Groups create a navigable hierarchy. Each group's `--help` shows only its subcommands. Each subcommand's `--help` shows only its options. An AI agent can drill into any branch without noise from unrelated commands.

### Show Help on Missing Args

Use a custom group class that shows full help instead of terse "Missing argument" errors when required arguments are omitted:

```python
class ShowHelpOnMissingArgs(click.Group):
    def resolve_command(self, ctx, args):
        cmd_name, cmd, remaining = super().resolve_command(ctx, args)
        if cmd is not None and not isinstance(cmd, click.Group):
            required_args = [p for p in cmd.params if isinstance(p, click.Argument) and p.required]
            if required_args and len(remaining) < len(required_args):
                with click.Context(cmd, info_name=cmd_name, parent=ctx) as sub_ctx:
                    click.echo(cmd.get_help(sub_ctx))
                ctx.exit(0)
        return cmd_name, cmd, remaining
```

### Root-Level Entry Point

The CLI is a single `cli.py` at the project root. It is independently executable with `if __name__ == "__main__"`.

```
project_root/
├── cli.py          # All CLI operations
├── .project_root   # Marker file
└── modules/        # Backend code (not entry points)
```

Scripts in `scripts/` are utility scripts outside the regular CLI surface.

---

## Technology Stack

| Concern | Solution |
|---------|----------|
| Framework | Click (groups + subcommands) |
| Output (tables, panels) | Rich |
| Output (simple text) | Click styling (`click.style`, `click.echo`) |
| Configuration | YAML via `get_app_config()` + secrets via `get_settings()` |
| Logging | structlog via `setup_logging()` + `get_logger()` |
| Project root | `validate_project_root()` from `modules.backend.core.config` |

---

## Required Options

Global options live on the root group only. They are not repeated on subcommands.

| Option | Short | Purpose |
|--------|-------|---------|
| `--verbose` | `-v` | Enable INFO level logging |
| `--debug` | `-d` | Enable DEBUG level logging |
| `--help` | | Show help (Click provides this automatically) |

The logging setup follows a strict pattern — no custom log level logic:

```python
if debug:
    log_level = "DEBUG"
elif verbose:
    log_level = "INFO"
else:
    log_level = "WARNING"

setup_logging(level=log_level, format_type="console")
```

---

## Implementation Pattern

### Root Group

The root group creates a shared context, shows help when called bare, and propagates `--verbose`/`--debug` to all subcommands:

```python
class CliContext:
    def __init__(self, verbose: bool, debug: bool):
        # ... logging setup ...
        self.logger = get_logger("cli")

@click.group(cls=ShowHelpOnMissingArgs, invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Enable INFO-level logging.")
@click.option("--debug", "-d", is_flag=True, help="Enable DEBUG-level logging.")
@click.pass_context
def cli(ctx, verbose: bool, debug: bool):
    """Platform CLI."""
    ctx.obj = CliContext(verbose, debug)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
```

### Simple Commands

Commands that need no subcommands are registered directly on the root group:

```python
@cli.command()
@click.pass_obj
def health(ctx):
    """Run local health checks."""
    from modules.backend.cli.health import check_health
    check_health(ctx.logger)
```

### Command Groups

Related operations are organized into groups. Each group shows help when called bare:

```python
@cli.group(cls=ShowHelpOnMissingArgs, invoke_without_command=True)
@click.pass_context
def server(ctx):
    """Manage the API server lifecycle."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

@server.command()
@click.option("--host", default=None, help="Server host.")
@click.option("--port", default=None, type=int, help="Server port.")
@click.option("--reload", is_flag=True, help="Enable auto-reload.")
@click.pass_obj
def start(ctx, host, port, reload):
    """Start the API server."""
    from modules.backend.cli.server import run_server
    run_server(ctx.logger, host, port, reload)
```

### Tree Command

The `tree` command renders the full CLI hierarchy for AI discoverability:

```python
@cli.command("tree")
def tree_cmd():
    """Show the full command tree with all options."""
    click.echo("cli")
    lines = _format_tree(cli)
    click.echo("\n".join(lines))
```

### CLI Handler Modules

Command logic lives in `modules/backend/cli/`. Each handler module exports a function that receives a logger and action-specific parameters. The CLI layer is a thin adapter — no business logic.

```python
# modules/backend/cli/mission.py
def run_mission(cli_logger, action, objective, mission_id, roster, budget, triggered_by, output_format):
    """Dispatch mission CLI actions."""
    # ...
```

---

## Output Formatting

### Rich Tables and Panels

Use Rich for structured output (tables, panels, color-coded status):

```python
from rich.console import Console
from rich.table import Table

console = Console(width=140)
table = Table(title="Missions", expand=True)
table.add_column("Status", no_wrap=True)
# ...
console.print(table)
```

### Simple Text

Use Click styling for simple messages:

| Output type | Format |
|------------|--------|
| Success | `click.style("text", fg="green")` |
| Error | `click.style("Error: text", fg="red")` to stderr |
| Warning | `click.style("Warning: text", fg="yellow")` |
| Progress | `click.echo` with status updates |

### Error Output

Errors go to stderr. Always include actionable guidance:

```python
click.echo(
    click.style("Error: Backend is not reachable.", fg="red"),
    err=True,
)
click.echo("Start it with: python cli.py server start", err=True)
sys.exit(1)
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Application error (bad input, backend unreachable, operation failed) |
| 2 | Usage error (Click handles this automatically for missing required options) |

### Async Exit Handling

Never call `sys.exit()` from inside async code (it causes output duplication with Click). Raise a custom exception and catch it in the synchronous caller:

```python
class _AbortMission(Exception):
    """Output already printed — just exit."""
    pass

def run_mission(...):
    try:
        asyncio.run(handler(...))
    except _AbortMission:
        sys.exit(1)
```

---

## Configuration

CLI scripts load configuration from the centralized config system — never from `~/.config` or local dotfiles:

- **Secrets**: `config/.env` via `get_settings()`
- **Application config**: `config/settings/*.yaml` via `get_app_config()`
- **Server URL/port**: `get_server_base_url()` from config, with `--port` override

No hardcoded URLs, ports, timeouts, or fallback defaults.

---

## Backend Communication

### HTTP Client

Use httpx for async HTTP calls with `X-Frontend-ID: cli`:

```python
import httpx

async with httpx.AsyncClient(
    base_url=base_url,
    timeout=timeout,
    headers={"X-Frontend-ID": "cli"},
) as client:
    response = await client.post("/api/v1/endpoint", json=payload)
```

### Connection Errors

Handle unreachable backend explicitly — fail fast, suggest the fix:

```python
except httpx.ConnectError:
    click.echo(click.style("Error: Backend is not reachable.", fg="red"), err=True)
    click.echo("Start it with: python cli.py server start", err=True)
    return 1
```

### Subprocess Execution

For launching services (uvicorn, taskiq, alembic), use `subprocess.run`:

```python
cmd = [sys.executable, "-m", "uvicorn", "modules.backend.main:app", "--host", host, "--port", str(port)]
try:
    subprocess.run(cmd, check=True)
except KeyboardInterrupt:
    logger.info("Server stopped")
except subprocess.CalledProcessError as e:
    logger.error("Server failed to start", extra={"exit_code": e.returncode})
    sys.exit(e.returncode)
```

---

## Testing

CLI scripts are tested via subprocess execution — real invocations, not mocked Click runners:

```python
import subprocess
import sys

def test_cli_help():
    result = subprocess.run(
        [sys.executable, "cli.py", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "server" in result.stdout
    assert "--verbose" in result.stdout

def test_server_help():
    result = subprocess.run(
        [sys.executable, "cli.py", "server", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "start" in result.stdout
```

---

## Adoption Checklist

When adopting this module:

- [ ] Create root-level `cli.py` with `@click.group(cls=ShowHelpOnMissingArgs, invoke_without_command=True)`
- [ ] Add `--verbose` and `--debug` options on the root group only
- [ ] Add `validate_project_root()` call in the root group callback
- [ ] Bind structlog source: `bind_context(source="cli")`
- [ ] Add `tree` command for full CLI discoverability
- [ ] Ensure every group shows help when called bare (`invoke_without_command=True`)
- [ ] Use Rich for tables and structured output
- [ ] Set `X-Frontend-ID: cli` on all HTTP requests
- [ ] Load all config from centralized `config/` — no local dotfiles
- [ ] Handle `httpx.ConnectError` with actionable error messages
- [ ] Never call `sys.exit()` from async code — use exception pattern
- [ ] Write subprocess-based tests (not mocked Click runners)
- [ ] Add usage examples in the script docstring

---

## Related Documentation

- [08-python-coding-standards.md](08-python-coding-standards.md) — Python conventions (imports, logging, file size)
- [03-backend-architecture.md](03-backend-architecture.md) — API design patterns consumed by CLI
- [10-observability.md](10-observability.md) — X-Frontend-ID, log sources, structured logging
- [01-core-principles.md](01-core-principles.md) — Thin client mandate (P1, P2)
- [27-tui-architecture.md](27-tui-architecture.md) — Interactive terminal interface (Textual) for persistent sessions
- [22-frontend-architecture.md](22-frontend-architecture.md) — Web frontend (React)
