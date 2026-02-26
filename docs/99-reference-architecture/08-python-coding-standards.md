# 08 - Python Coding Standards

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic Python coding standards

---

## Scope

This document defines coding standards for Python backend development. It covers file organization, code structure, configuration, error handling, and tooling.

---

## Context

Coding standards exist because code is read far more often than it is written, and inconsistent style creates friction every time a developer (or an AI assistant) works with unfamiliar code. This document removes style decisions from individual developers by standardizing Python file organization, import conventions, configuration patterns, error handling, and tooling for all backend projects.

The driving insight is that most Python code quality issues stem from a small set of recurring problems: relative imports that break when files move, hardcoded values scattered across modules, inconsistent logging that makes debugging impossible, and files that grow until they are unreadable. Each standard directly addresses one of these: absolute imports only, centralized configuration via Pydantic Settings with no hardcoded fallbacks, structured logging via `structlog`, and file size limits (target 300-400 lines, hard limit 500).

Every CLI script must include `--verbose` and `--debug` flags because the cost of adding them later — during a production incident, when you need them most — is far higher than including them upfront. Timezone handling is standardized to naive UTC datetimes because mixing timezone-aware and timezone-naive objects is a persistent source of subtle bugs. These standards are enforced by the development workflow (13) through pre-commit hooks and CI checks, and complement the TypeScript standards (11) for frontend development.

---

## File Organization

### Project Structure

```
project/
├── .git/
├── .cursor/rules/
├── .gitignore
├── .project_root
├── README.md
├── requirements.txt
├── config/
│   ├── .env
│   ├── .env.example
│   └── settings/
│       └── *.yaml
├── docs/
├── scripts/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── modules/
│   └── backend/
│       ├── main.py
│       ├── api/
│       ├── core/
│       ├── models/
│       ├── repositories/
│       ├── schemas/
│       └── services/
└── data/
    └── logs/
```

### File Size Limits

| File Type | Maximum Lines | Target |
|-----------|---------------|--------|
| Modules | 500 | ~300-400 |
| Entry scripts | 300 | ~200 |
| Test files | 600 | ~400 |
| Config files | 200 | ~100 |

Files exceeding limits must be split into focused submodules.

### File Naming

- Modules: `lowercase_with_underscores.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Interfaces: `IServiceName` prefix

---

## Import Standards

### Import Order

Organize imports in groups separated by blank lines:

1. Standard library imports
2. Third-party imports
3. Local application imports

### Absolute Imports Only

```python
# Correct
from modules.backend.services.user import UserService
from config.settings import settings

# Forbidden
from .user import UserService
from ..services import UserService
```

Relative imports are **never permitted**.

### Import Organization Tools

Use `isort` with configuration:

```ini
[tool.isort]
profile = "black"
line_length = 100
known_first_party = ["modules", "config"]
```

---

## Configuration Management

### No Hardcoded Values

All configuration comes from:

- Environment variables (`.env` file)
- YAML configuration files
- Never from code

```python
# Forbidden
DATABASE_URL = "postgresql://localhost/mydb"
TIMEOUT = 30

# Required
DATABASE_URL = settings.database.url
TIMEOUT = settings.api.timeout
```

### No Hardcoded Fallbacks

```python
# Forbidden
url = os.getenv("API_URL", "http://localhost:8000")

# Required - fail fast if missing
url = settings.api.url  # Pydantic validates at startup
```

### Configuration Structure

```python
# config/settings.py
from pydantic_settings import BaseSettings

class DatabaseSettings(BaseSettings):
    host: str
    port: int
    name: str
    
    class Config:
        env_prefix = "DB_"

class Settings(BaseSettings):
    database: DatabaseSettings
    
settings = Settings()
```

### Project Root Detection

Use `.project_root` marker file:

```python
def find_project_root() -> Path:
    current = Path.cwd()
    while current != current.parent:
        if (current / ".project_root").exists():
            return current
        current = current.parent
    raise RuntimeError("Project root not found")
```

---

## CLI Standards

### Command Structure

Use subcommands for complex CLIs:

```bash
# Recommended for complex CLIs
mycli auth login
mycli project create --name test
mycli data export --format csv
```

Use flat structure with `--action` for simple CLIs:

```bash
# Acceptable for simple CLIs
myscript --action create --name test
```

### Required Options

All scripts must implement:

| Option | Purpose |
|--------|---------|
| `--help` | Detailed help information |
| `--verbose` | Enable verbose logging (INFO level) |
| `--debug` | Enable debug logging (DEBUG level) |

### Implementation Pattern

```python
import click
from modules.backend.core.logging import setup_logging

@click.group()
@click.option('--verbose', is_flag=True, help='Enable verbose output')
@click.option('--debug', is_flag=True, help='Enable debug output')
@click.pass_context
def cli(ctx, verbose: bool, debug: bool):
    ctx.ensure_object(dict)
    log_level = 'DEBUG' if debug else 'INFO' if verbose else 'WARNING'
    setup_logging(level=log_level)
    ctx.obj['verbose'] = verbose

@cli.command()
@click.option('--name', required=True)
@click.pass_context
def create(ctx, name: str):
    """Create a new resource."""
    # Implementation
```

---

## Logging Standards

### Centralized Logging

All modules use the centralized logging system:

```python
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)
```

Never create standalone loggers:

```python
# Forbidden
import logging
logger = logging.getLogger(__name__)
```

### Log Levels

| Level | Use For |
|-------|---------|
| DEBUG | Detailed diagnostic information |
| INFO | Confirmation of expected behavior |
| WARNING | Unexpected but handled situations |
| ERROR | Failures that prevent operation completion |
| CRITICAL | System-wide failures |

### Log Content

Include context in all log messages:

```python
# Good
logger.info("Task completed", extra={"task_id": task.id, "duration": elapsed})

# Bad
logger.info("Done")
```

---

## Error Handling

### Custom Exceptions

Define domain-specific exceptions:

```python
class ApplicationError(Exception):
    """Base exception for all application errors."""
    pass

class NotFoundError(ApplicationError):
    """Raised when a resource cannot be found."""
    pass

class ValidationError(ApplicationError):
    """Raised when validation fails."""
    pass
```

### Error Handling Pattern

```python
try:
    result = await service.execute(task)
except NotFoundError:
    logger.warning("Resource not found", extra={"id": resource_id})
    raise HTTPException(status_code=404, detail="Resource not found")
except ValidationError as e:
    logger.warning("Validation failed", extra={"error": str(e)})
    raise HTTPException(status_code=422, detail=str(e))
```

### Never Silence Exceptions

```python
# Forbidden
try:
    risky_operation()
except Exception:
    pass

# Required
try:
    risky_operation()
except SpecificError as e:
    logger.error("Operation failed", extra={"error": str(e)})
    raise
```

---

## Type Hints

### Required Everywhere

All functions must have complete type hints:

```python
def process_task(
    task_id: UUID,
    options: TaskOptions,
    timeout: int = 30
) -> TaskResult:
    ...
```

### Common Patterns

```python
from typing import Optional, List, Dict, Any
from uuid import UUID

# Optional parameters
def find_resource(resource_id: UUID) -> Optional[Resource]: ...

# Collections
def list_resources(project_id: UUID) -> List[Resource]: ...

# Dictionaries
def get_config() -> Dict[str, Any]: ...
```

### Type Checking

Run mypy in CI:

```bash
mypy modules/backend --strict
```

---

## Docstrings

### Required For

- All public modules
- All public classes
- All public functions/methods

### Format

```python
def execute_task(task: Task, context: Context) -> TaskResult:
    """Execute a task with the given context.
    
    Args:
        task: The task to execute.
        context: Execution context with dependencies.
    
    Returns:
        TaskResult containing output and status.
    
    Raises:
        NotFoundError: If the task doesn't exist.
        ExecutionError: If execution fails.
    """
```

---

## Datetime Handling

### Timezone-Naive UTC Only

All datetimes stored in the database are timezone-naive UTC.

### Getting Current UTC Time

```python
from datetime import datetime, timezone

# Correct - timezone-naive UTC
created_at = datetime.now(timezone.utc).replace(tzinfo=None)

# Also correct - use project helper
from modules.backend.core.utils import utc_now
created_at = utc_now()
```

### Forbidden Patterns

```python
# WRONG - returns local time, not UTC
created_at = datetime.now()

# WRONG - deprecated in Python 3.12+
created_at = datetime.utcnow()

# WRONG - timezone-aware datetime causes PostgreSQL issues
created_at = datetime.now(timezone.utc)
```

### Project Helper Function

```python
# modules/backend/core/utils.py
from datetime import datetime, timezone

def utc_now() -> datetime:
    """Return current UTC time as timezone-naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
```

### Conversion Rules

- **Store**: Always timezone-naive UTC in database
- **Display**: Convert to user timezone at presentation layer only
- **Accept**: Convert user input to UTC immediately upon receipt
- **Compare**: All datetime comparisons use UTC

---

## Testing Standards

See **11-testing-standards.md** for comprehensive testing guidance including:

- Test directory structure (hybrid approach)
- Test types (unit, integration, e2e)
- Fixture patterns and conftest hierarchy
- Mocking strategies
- Coverage requirements

### Quick Reference

```bash
# Run by test type
pytest tests/unit                    # Fast, isolated
pytest tests/integration             # With real DB
pytest tests/e2e                     # Full stack

# Run with coverage
pytest tests/unit --cov=modules/backend
```

---

## Code Quality Tools

### Required Tools

| Tool | Purpose | Config |
|------|---------|--------|
| black | Code formatting | `pyproject.toml` |
| isort | Import sorting | `pyproject.toml` |
| flake8 | Linting | `.flake8` |
| mypy | Type checking | `mypy.ini` |

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    hooks:
      - id: black
  - repo: https://github.com/pycqa/isort
    hooks:
      - id: isort
  - repo: https://github.com/pycqa/flake8
    hooks:
      - id: flake8
```

---

## Dependency Injection

### Constructor Injection

```python
class UserService:
    def __init__(
        self,
        repository: UserRepository,
        event_bus: EventBus
    ):
        self._repository = repository
        self._event_bus = event_bus
```

### Avoid Service Locators

```python
# Forbidden
class UserService:
    def execute(self):
        repo = ServiceLocator.get(UserRepository)
        
# Required
class UserService:
    def __init__(self, repository: UserRepository):
        self._repository = repository
```

---

## Anti-Patterns

### Forbidden Practices

- Hardcoded values in code
- Hardcoded fallback defaults
- Relative imports
- Global mutable state
- Silenced exceptions
- Missing type hints
- Files over 500 lines
- Business logic in `__init__.py`
- Circular imports
- Deep nesting (>3-4 levels)
- Timezone-aware datetimes in database

### Required Practices

- Absolute imports
- Centralized configuration
- Centralized logging
- Type hints on all functions
- Docstrings on public APIs
- --verbose and --debug on all CLIs
- Error handling with context
- Constructor dependency injection

---

## Version Control

### Commit Messages

```
[TYPE] Short summary (max 72 chars)

- Detailed explanation
- List of changes
- Issue references

Types: FEAT, FIX, REFACTOR, DOCS, TEST, CHORE
```

### Commit Rules

- Only commit working code
- Run tests before committing
- Never commit secrets or `.env` files
