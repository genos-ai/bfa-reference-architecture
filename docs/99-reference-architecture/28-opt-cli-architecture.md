# 28 - CLI Architecture (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-02-26*

## Changelog

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

The core architecture mandates that clients are stateless presentation layers (P2) with no business logic (P1). The CLI is the simplest expression of this — a script that accepts options, calls the backend, and displays the result.

CLI scripts live in the project root (not a separate `cli/` package). Each script is a single `@click.command()` with `--options` for all parameters. No subcommands, no positional arguments, no `@click.group()`. This keeps every script independently executable, grep-friendly, and trivial for AI assistants to understand.

The project has three root entry scripts, each serving a different purpose:

| Script | Purpose | Interaction model |
|--------|---------|-------------------|
| `cli.py` | Service lifecycle and admin operations | `--service` + `--action` |
| `chat.py` | One-shot message to backend agents/services | `--message` + `--agent` |
| `tui.py` | Launch interactive terminal interface | (no options beyond `--verbose`/`--debug`) |

All three follow identical patterns: Click, `--verbose`/`--debug`, centralized logging, `validate_project_root()`, source binding via structlog.

---

## Design Rules

### Options Over Subcommands

All CLI functionality is controlled through `--options`. Never use positional arguments or subcommands.

```bash
# Correct: options
python cli.py --service server --action start --verbose
python chat.py --message "check health" --agent system.health.agent --raw

# Wrong: subcommands
python cli.py server start
python chat.py send "check health"

# Wrong: positional arguments
python cli.py server
python chat.py "check health"
```

**Rationale**: Options are self-documenting (`--help` shows all of them), order-independent, and unambiguous. Subcommands create nested help trees that are harder for both humans and AI to navigate. Options work consistently with `click.Choice` for constrained values.

### Root-Level Entry Scripts

CLI scripts live in the project root directory, not in a package. Each is an independently executable Python file with `if __name__ == "__main__"`.

```
project_root/
├── cli.py          # Service lifecycle, admin
├── chat.py         # One-shot messaging
├── tui.py          # Interactive terminal
├── .project_root   # Marker file
└── modules/        # Backend code (not entry points)
```

Scripts in `scripts/` are exceptions — utility scripts that are not part of the regular CLI surface.

### One Command Per Script

Each script is a single `@click.command()`, not a `@click.group()`. If a script grows too many options, split it into a new script rather than adding subcommands.

---

## Technology Stack

| Concern | Solution |
|---------|----------|
| Framework | Click |
| HTTP Client | httpx (async) |
| Output formatting | Click styling (`click.style`, `click.echo`) + Rich (for complex output) |
| Configuration | YAML via `get_app_config()` + secrets via `get_settings()` |
| Logging | structlog via `setup_logging()` + `get_logger()` |
| Project root | `validate_project_root()` from `modules.backend.core.config` |

---

## Required Options

Every root-level CLI script must include these options:

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

### Standard Script Template

Every CLI script follows this structure:

```python
#!/usr/bin/env python3
"""
Script description.

Usage:
    python script.py --help
    python script.py --option value --verbose
"""

import sys
from pathlib import Path

import click
import structlog

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.core.config import validate_project_root
from modules.backend.core.logging import get_logger, setup_logging


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output (INFO level logging).")
@click.option("--debug", "-d", is_flag=True, help="Enable debug output (DEBUG level logging).")
def main(verbose: bool, debug: bool) -> None:
    """Script description shown in --help."""
    validate_project_root()

    if debug:
        log_level = "DEBUG"
    elif verbose:
        log_level = "INFO"
    else:
        log_level = "WARNING"

    setup_logging(level=log_level, format_type="console")
    structlog.contextvars.bind_contextvars(source="cli")
    logger = get_logger(__name__)

    # Script logic here


if __name__ == "__main__":
    main()
```

### Service Lifecycle Pattern

For scripts that manage long-running services, use `--service` and `--action`:

```python
@click.command()
@click.option(
    "--service", "-s",
    type=click.Choice(["server", "worker", "scheduler"]),
    default="server",
    help="Service to manage.",
)
@click.option(
    "--action", "-a",
    type=click.Choice(["start", "stop", "restart", "status"]),
    default="start",
    help="Lifecycle action.",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.option("--debug", "-d", is_flag=True, help="Enable debug output.")
@click.option("--port", default=None, type=int, help="Override server port.")
def main(service: str, action: str, verbose: bool, debug: bool, port: int | None) -> None:
    """Application service manager."""
    # ...
```

### One-Shot Operation Pattern

For scripts that perform a single operation and exit:

```python
@click.command()
@click.option("--message", "-m", required=True, help="Message to send.")
@click.option("--raw", is_flag=True, help="Output raw JSON response.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.option("--debug", "-d", is_flag=True, help="Enable debug output.")
def main(message: str, raw: bool, verbose: bool, debug: bool) -> None:
    """Send a message to the backend."""
    # ...
```

---

## Output Formatting

### Conventions

| Output type | Format |
|------------|--------|
| Success | `click.style("text", fg="green")` |
| Error | `click.style("Error: text", fg="red")` to stderr |
| Warning | `click.style("Warning: text", fg="yellow")` |
| Data (human) | Tables via Rich or formatted `click.echo` |
| Data (machine) | JSON via `--raw` flag |
| Progress | `click.echo` with status updates |

### Error Output

Errors go to stderr. Always include actionable guidance:

```python
click.echo(
    click.style("Error: Backend is not reachable.", fg="red"),
    err=True,
)
click.echo("Start it with: python cli.py --service server", err=True)
sys.exit(1)
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Application error (bad input, backend unreachable, operation failed) |
| 2 | Usage error (Click handles this automatically for missing required options) |

---

## Configuration

CLI scripts load configuration from the centralized config system — never from `~/.config` or local dotfiles:

- **Secrets**: `config/.env` via `get_settings()`
- **Application config**: `config/settings/*.yaml` via `get_app_config()`
- **Server URL/port**: `get_server_base_url()` from config, with `--port` override

```python
from modules.backend.core.config import get_app_config, get_server_base_url

base_url, timeout = get_server_base_url()
if port:
    host = get_app_config().application.server.host
    base_url = f"http://{host}:{port}"
```

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
    click.echo("Start it with: python cli.py --service server", err=True)
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
    assert "--service" in result.stdout
    assert "--verbose" in result.stdout

def test_cli_health():
    result = subprocess.run(
        [sys.executable, "cli.py", "--service", "health", "--verbose"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
```

---

## Adoption Checklist

When adopting this module:

- [ ] Create root-level entry script with `@click.command()` (not `@click.group()`)
- [ ] Add `--verbose` and `--debug` options with standard logging setup
- [ ] Add `validate_project_root()` call
- [ ] Bind structlog source: `structlog.contextvars.bind_contextvars(source="cli")`
- [ ] Set `X-Frontend-ID: cli` on all HTTP requests
- [ ] Load all config from centralized `config/` — no local dotfiles
- [ ] Handle `httpx.ConnectError` with actionable error messages
- [ ] Add `--raw` flag if the script outputs structured data
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
