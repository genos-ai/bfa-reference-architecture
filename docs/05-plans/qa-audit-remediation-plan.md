# QA Audit Remediation Plan

**Source:** QA audit conducted 2026-02-26 on branch `feature/agent-system-rebuild`
**Findings:** 77 total (8 CRITICAL, 23 HIGH, 30 MEDIUM, 16 LOW)

---

## Instructions for Executing Agent

This plan is divided into 9 phases. Execute them **in order** — later phases depend on earlier ones. Each task has:
- **Audit ref** — finding number from the audit report
- **File** — exact path relative to project root
- **Current code** — the problematic snippet to locate
- **Fix** — what to do (not how — use your judgement on implementation)
- **Verify** — a command to confirm the fix is correct

**Rules you must follow while fixing:**
- All configuration from `config/settings/*.yaml` or `config/agents/*.yaml`. All secrets from `config/.env`. No hardcoded fallbacks.
- Absolute imports only: `from modules.backend.core.config import ...`
- Centralized logging only: `from modules.backend.core.logging import get_logger`
- Use `from modules.backend.core.utils import utc_now` for datetimes. Never `datetime.now()` or `datetime.utcnow()`.
- `__init__.py` files: docstring and exports only, no logic.
- Read the AGENTS.md file at the project root before starting. It is the canonical reference.

**Commit after each phase.** Use message format: `fix: phase N — <short description>`

---

## Phase 0 — Preparation

### Task 0.1: Create safety branch

```bash
git add -A && git stash
git checkout -b fix/qa-audit-remediation
git stash pop
```

No code changes in this phase.

---

## Phase 1 — Extend YAML Config with Missing Keys

Many code fixes in later phases replace hardcoded values with config reads. Those config keys must exist first. This phase adds them.

### Task 1.1: Add `scheme` to `ApplicationSchema` and `application.yaml`

**Audit ref:** #22
**Why:** `config.py:201` and `chat.py:345` hardcode `http://`. The scheme must come from config.

**File:** `config/settings/application.yaml`
**Action:** Add `scheme: "http"` under the `server:` section, between `host` and `port`. Update the commented options block at the top to include `scheme - URL scheme (string: http|https)`.

**File:** `modules/backend/core/config_schema.py`
**Action:** Find the `ServerSchema` class (or equivalent server model). Add a `scheme: str` field.

**Verify:**
```bash
rg 'scheme' config/settings/application.yaml
rg 'scheme.*str' modules/backend/core/config_schema.py
```

### Task 1.2: Add `db_driver`, `db_driver_async`, `redis_scheme` to `database.yaml`

**Audit ref:** #31
**Why:** `config.py:176,189` hardcodes `postgresql+asyncpg` and `redis://`.

**File:** `config/settings/database.yaml`
**Action:** Add these keys at the top level, before `host`:
```yaml
driver: "postgresql"
driver_async: "postgresql+asyncpg"
```
And under the `redis:` section:
```yaml
scheme: "redis"
```
Update the commented options block at the top of the file to document these.

**File:** `modules/backend/core/config_schema.py`
**Action:** Add `driver: str` and `driver_async: str` fields to the database schema. Add `scheme: str` to the redis sub-schema.

**Verify:**
```bash
rg 'driver' config/settings/database.yaml
rg 'scheme' config/settings/database.yaml
```

### Task 1.3: Add `expire_on_commit` to `database.yaml`

**Audit ref:** #(core audit F07)
**Why:** `database.py:68` hardcodes `expire_on_commit=False`.

**File:** `config/settings/database.yaml`
**Action:** Add `expire_on_commit: false` at the same level as `echo:`. Update the commented options block.

**File:** `modules/backend/core/config_schema.py`
**Action:** Add `expire_on_commit: bool = False` to the database schema (note: default in schema is acceptable for Pydantic schemas, it's the *code reading it* that must not hardcode).

**Verify:**
```bash
rg 'expire_on_commit' config/settings/database.yaml
```

### Task 1.4: Add `api_key_length` and `api_key_prefix` to `security.yaml`

**Audit ref:** #37
**Why:** `security.py:120-121` hardcodes `32` and `"app_"`.

**File:** `config/settings/security.yaml`
**Action:** Add a new section after `secrets_validation`:
```yaml
api_keys:
  key_length: 32
  prefix: "app_"
```
Update the commented options block at the top.

**File:** `modules/backend/core/config_schema.py`
**Action:** Add an `ApiKeysSchema` and nest it in `SecuritySchema`.

**Verify:**
```bash
rg 'key_length|prefix' config/settings/security.yaml
```

### Task 1.5: Add `third_party_log_levels` to `logging.yaml`

**Audit ref:** #33
**Why:** `logging.py:210-211` hardcodes logger names and levels.

**File:** `config/settings/logging.yaml`
**Action:** Add after the `handlers:` section:
```yaml
third_party_overrides:
  uvicorn.access: "WARNING"
  sqlalchemy.engine: "WARNING"
```
Update the commented options block.

**File:** `modules/backend/core/config_schema.py`
**Action:** Add `third_party_overrides: dict[str, str] = {}` to the logging schema.

**Verify:**
```bash
rg 'third_party_overrides' config/settings/logging.yaml
```

### Task 1.6: Add `valid_sources` to `logging.yaml`

**Audit ref:** #32
**Why:** `logging.py:51-60` hardcodes `VALID_SOURCES`.

**File:** `config/settings/logging.yaml`
**Action:** Add before `handlers:`:
```yaml
valid_sources:
  - "web"
  - "cli"
  - "tui"
  - "mobile"
  - "telegram"
  - "api"
  - "tasks"
  - "internal"
```
Update the commented options block.

**File:** `modules/backend/core/config_schema.py`
**Action:** Add `valid_sources: list[str]` to the logging schema.

**Verify:**
```bash
rg 'valid_sources' config/settings/logging.yaml
```

### Task 1.7: Add `scheduled_tasks` to a new `config/settings/tasks.yaml`

**Audit ref:** #49
**Why:** `scheduled.py:142-168` hardcodes the entire `SCHEDULED_TASKS` dict with cron expressions.

**File:** `config/settings/tasks.yaml` (new file)
**Action:** Create this file with the standard commented options block at the top, containing:
```yaml
scheduled:
  daily_cleanup:
    cron: "0 2 * * *"
    older_than_days: 30
    retry_on_error: false
  hourly_health_check:
    cron: "0 * * * *"
    retry_on_error: false
  weekly_report_generation:
    cron: "0 6 * * 0"
    retry_on_error: true
    max_retries: 2
  metrics_aggregation:
    cron: "*/15 * * * *"
    interval_minutes: 15
    retry_on_error: false
```

**File:** `modules/backend/core/config_schema.py`
**Action:** Add a `TasksSchema` with a `scheduled` dict field. Add it to `AppConfig` in `config.py` as a new property loading `tasks.yaml`.

**Verify:**
```bash
test -f config/settings/tasks.yaml && echo "OK"
rg 'tasks.yaml' modules/backend/core/config.py
```

**Commit phase 1.**

---

## Phase 2 — CRITICAL Security Fix

### Task 2.1: Fix P8 empty-allowlist-allows-all violation

**Audit ref:** #1, #2
**Criticality:** CRITICAL

**File:** `modules/telegram/middlewares/auth.py`
**Current code (lines 92-100):**
```python
if not authorized_users:
    logger.debug(
        "No authorized users configured, allowing all",
        extra={"user_id": user_id},
    )
    data["user_role"] = "admin"
    data["telegram_user"] = user
    return await handler(event, data)
```
**Fix:** Invert the logic. When `authorized_users` is empty, **deny** access (return `None`). Log a warning that no users are configured so all access is denied. Remove the `data["user_role"] = "admin"` grant.

**File:** `config/settings/application.yaml`
**Current code (line 26):**
```yaml
#     authorized_users - Authorized user IDs (list of integers, empty = allow all)
```
**Fix:** Change the comment to `empty = deny all` to match P8 principle.

**Verify:**
```bash
rg 'allow all' modules/telegram/middlewares/auth.py  # should return 0 matches
rg 'deny all' modules/telegram/middlewares/auth.py   # should match
rg 'empty = deny' config/settings/application.yaml   # should match
```

**Commit phase 2.**

---

## Phase 3 — Rewrite `scripts/dead_code_detector.py`

This file violates 7 rules simultaneously. It needs a full rewrite to project standards.

**Audit ref:** #13, #14, #15, #16, #17, #18, #19

### Task 3.1: Rewrite to project standards

**File:** `scripts/dead_code_detector.py`

**All of these must be fixed:**

1. **Replace `argparse` with `click`** (line 558). Use `@click.command()` with `@click.option()` decorators. Match the pattern in `scripts/compliance_checker.py`.

2. **Replace positional argument with `--path` option** (line 577-581). Change `parser.add_argument('path', nargs='?', default='.')` to `@click.option("--path", default=".", help="...")`.

3. **Replace `import logging` with centralized logging** (line 24, 35-47, 64, 608). Remove `import logging`, remove the custom `setup_logging()` function, and use:
   ```python
   from modules.backend.core.logging import get_logger, setup_logging
   ```
   Call `setup_logging(level=..., format_type="console")` at the start of `main()` like `compliance_checker.py` does. Replace `self.logger = logging.getLogger(__name__)` with `self.logger = get_logger(__name__)`.

4. **Fix `sys.path` insertion** (line 32). Change from `sys.path.insert(0, str(Path(__file__).parent))` to `sys.path.insert(0, str(Path(__file__).parent.parent))` — must point to project root, not `scripts/` directory. Follow the pattern in `compliance_checker.py:22-23`.

5. **Replace `datetime.now()` with `utc_now()`** (line 429). Import and use `from modules.backend.core.utils import utc_now`. Change `datetime.now().isoformat()` to `utc_now().isoformat()`.

6. **Remove bare `except:` clauses** (lines 439, 490). Line 439: change `except:` to `except OSError:` (the only expected exception from `stat()`). Line 490: change `except:` to `except (OSError, SyntaxError):` and log the error instead of silently passing.

7. **Replace `print()` with `click.echo()`** (lines 629, 631). Change `print(f"\n📄 Report saved to: {args.output}")` to `click.echo(...)` and `print(report)` to `click.echo(report)`.

**Verify:**
```bash
rg 'import logging' scripts/dead_code_detector.py        # 0 matches
rg 'import argparse' scripts/dead_code_detector.py       # 0 matches
rg 'datetime\.now\(\)' scripts/dead_code_detector.py     # 0 matches
rg 'except:' scripts/dead_code_detector.py               # 0 matches
rg 'print\(' scripts/dead_code_detector.py               # 0 matches
rg 'import click' scripts/dead_code_detector.py          # 1 match
rg 'parent\.parent' scripts/dead_code_detector.py        # 1 match
```

**Commit phase 3.**

---

## Phase 4 — Agent System Hardcoded Fallbacks

The agent system has a fallback chain: missing `coordinator.yaml` → returns `{}` → every `.get("key", default)` silently activates. Fix from the top down.

### Task 4.1: Make `coordinator.yaml` load fail-fast

**Audit ref:** #5
**File:** `modules/backend/agents/coordinator/middleware.py`
**Current code (lines 35-38):**
```python
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}
```
**Fix:** Remove the `return {}` fallback. If the file doesn't exist, raise `FileNotFoundError`. Also change `or {}` to an explicit None check that raises `ValueError` if the file is empty/null.

**Verify:**
```bash
rg 'return \{\}' modules/backend/agents/coordinator/middleware.py  # 0 matches
```

### Task 4.2: Remove hardcoded fallback limits in coordinator

**Audit ref:** #6
**File:** `modules/backend/agents/coordinator/coordinator.py`
**Current code (lines 133-134):**
```python
        request_limit=limits.get("max_requests_per_task", 10),
        total_tokens_limit=limits.get("max_tokens_per_task", 50000),
```
**Fix:** Replace `.get("key", default)` with direct key access `limits["max_requests_per_task"]` and `limits["max_tokens_per_task"]`. If the key is missing, let it raise `KeyError` — the config is mandatory.

**Verify:**
```bash
rg 'limits\.get\(' modules/backend/agents/coordinator/coordinator.py  # 0 matches
```

### Task 4.3: Remove hardcoded fallback in guardrails `max_input_length`

**Audit ref:** #41
**File:** `modules/backend/agents/coordinator/middleware.py`
**Current code (line 67):**
```python
            coordinator_max = guardrails.get("max_input_length", 32000)
```
**Fix:** Change to `coordinator_max = guardrails["max_input_length"]`. The key is defined in `coordinator.yaml` and must be present.

**Verify:**
```bash
rg '32000' modules/backend/agents/coordinator/middleware.py  # 0 matches
```

### Task 4.4: Remove hardcoded fallback model names in agents

**Audit ref:** #3, #4
**File:** `modules/backend/agents/vertical/code/qa/agent.py`
**Current code (lines 130, 175):**
```python
    model = deps.config.get("model", "anthropic:claude-haiku-4-5-20251001")
```
**Fix:** Change both occurrences to `model = deps.config["model"]`. The model is defined in `config/agents/code/qa/agent.yaml` and must be present.

**File:** `modules/backend/agents/vertical/system/health/agent.py`
**Current code (line 60):**
```python
    model = deps.config.get("model", "anthropic:claude-haiku-4-5-20251001")
```
**Fix:** Same — change to `model = deps.config["model"]`.

**Verify:**
```bash
rg 'claude-haiku' modules/backend/agents/vertical/  # 0 matches
```

### Task 4.5: Remove hardcoded fallback `agent_type` in registry

**Audit ref:** #40
**File:** `modules/backend/agents/coordinator/registry.py`
**Current code (line 95):**
```python
        agent_type = config.get("agent_type", "vertical")
```
**Fix:** Change to `agent_type = config["agent_type"]`. Every agent YAML must declare its type.

**Verify:**
```bash
rg '"vertical"' modules/backend/agents/coordinator/registry.py  # 0 matches
```

### Task 4.6: Fix global mutable state — API key injection

**Audit ref:** #7
**File:** `modules/backend/agents/coordinator/coordinator.py`
**Current code (lines 47-57):**
```python
_api_key_set = False

def _ensure_api_key() -> None:
    global _api_key_set
    if _api_key_set:
        return
    settings = get_settings()
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    _api_key_set = True
```
**Fix:** Remove the global `_api_key_set` flag. Instead, pass the API key directly when creating the PydanticAI model. Look at how PydanticAI's `Agent` accepts model configuration and pass the key through there. Remove the `os.environ.setdefault` call. If PydanticAI requires the env var approach, keep the function but document why and remove the global boolean — use `os.environ.get("ANTHROPIC_API_KEY")` as the idempotency check instead.

**Verify:**
```bash
rg '_api_key_set' modules/backend/agents/coordinator/coordinator.py  # 0 matches ideally, or documented exception
```

### Task 4.7: Fix unbounded `_conversations` dict (memory leak)

**Audit ref:** #8
**File:** `modules/backend/agents/vertical/code/qa/agent.py`
**Current code (line 152):**
```python
_conversations: dict[str, list] = {}
```
**Fix:** Replace with a bounded LRU-style cache. Use `functools.lru_cache` or a custom `OrderedDict`-based implementation with a max size read from agent config. At minimum, add an eviction mechanism (e.g., max 100 conversations, evict oldest on overflow). The max should come from the agent YAML config — add a `max_conversations` key to `config/agents/code/qa/agent.yaml`.

**Verify:**
```bash
rg '_conversations: dict' modules/backend/agents/vertical/code/qa/agent.py  # 0 matches
```

### Task 4.8: Remove hardcoded defaults in `coordinator/models.py`

**Audit ref:** #29
**File:** `modules/backend/agents/coordinator/models.py`
**Current code (lines 21-23):**
```python
    channel: str = "api"
    session_type: str = "direct"
    tool_access_level: str = "sandbox"
```
**Fix:** Remove the default values so callers must explicitly provide them. The coordinator that creates these objects should read the values from config.

**Verify:**
```bash
rg 'channel: str = "api"' modules/backend/agents/coordinator/models.py  # 0 matches
```

### Task 4.9: Fix `max_delegation_depth` to read from config

**Audit ref:** #42
**File:** `modules/backend/agents/deps/base.py`
**Current code (line 84):**
```python
    max_delegation_depth: int = 2
```
**Fix:** Remove the default. The caller (coordinator) must pass this from `coordinator.yaml` `routing.max_routing_depth`.

**Verify:**
```bash
rg 'max_delegation_depth: int = 2' modules/backend/agents/deps/base.py  # 0 matches
```

### Task 4.10: Fix conflicting `max_length` in agents endpoint

**Audit ref:** #11
**File:** `modules/backend/api/v1/endpoints/agents.py`
**Current code (line 29):**
```python
        max_length=1000,
```
**Fix:** Read `max_input_length` from coordinator config (loaded via `get_app_config()` or the coordinator's `_load_coordinator_config()`). Use that value in the Pydantic `Field(max_length=...)`. If a dynamic Field isn't feasible, validate in the endpoint body instead of the schema.

**Verify:**
```bash
rg 'max_length=1000' modules/backend/api/v1/endpoints/agents.py  # 0 matches
```

### Task 4.11: Fix private function import across module boundary

**Audit ref:** #10
**File:** `modules/backend/api/v1/endpoints/agents.py`
**Current code (line 99):**
```python
        from modules.backend.agents.coordinator.coordinator import _route
```
**Fix:** Rename `_route` to `route` (make it public) in `coordinator.py`, or create a public wrapper function. Update the import in `agents.py` to use the public name.

**Verify:**
```bash
rg '_route' modules/backend/api/v1/endpoints/agents.py  # 0 matches
```

### Task 4.12: Break bidirectional dependency between agents and coordinator

**Audit ref:** #12
**File:** `modules/backend/agents/vertical/code/qa/agent.py` (line 14) and `modules/backend/agents/vertical/system/health/agent.py` (line 13)
**Current code:**
```python
from modules.backend.agents.coordinator.coordinator import assemble_instructions
```
**Fix:** Move `assemble_instructions()` out of `coordinator/coordinator.py` into a new shared module `modules/backend/agents/prompts.py`. Update imports in both vertical agents and in `coordinator.py` to import from the new location.

**Verify:**
```bash
rg 'from modules.backend.agents.coordinator.coordinator import assemble_instructions' modules/  # 0 matches
rg 'from modules.backend.agents.prompts import assemble_instructions' modules/  # 2+ matches
```

### Task 4.13: Add missing `RequestId` injection to streaming endpoint

**Audit ref:** #44
**File:** `modules/backend/api/v1/endpoints/agents.py`
**Current code (line 93):**
```python
async def agent_chat_stream(data: ChatRequest) -> StreamingResponse:
```
**Fix:** Add `request_id: RequestId` parameter to match the other endpoints (`agent_chat` and `agent_registry`).

**Verify:**
```bash
rg 'def agent_chat_stream.*RequestId' modules/backend/api/v1/endpoints/agents.py  # 1 match
```

**Commit phase 4.**

---

## Phase 5 — Core Module Fixes

### Task 5.1: Fix silent `or {}` in YAML loader

**Audit ref:** #23
**File:** `modules/backend/core/config.py`
**Current code (line 69):**
```python
        return yaml.safe_load(f) or {}
```
**Fix:** Replace with explicit check:
```python
        result = yaml.safe_load(f)
        if result is None:
            raise ValueError(f"Configuration file is empty: {config_path}")
        return result
```

**Verify:**
```bash
rg 'or \{\}' modules/backend/core/config.py  # 0 matches
```

### Task 5.2: Use config for DB/Redis URL construction

**Audit ref:** #31, #22
**File:** `modules/backend/core/config.py`
**Current code (lines 176-177):**
```python
    driver = "postgresql+asyncpg" if async_driver else "postgresql"
    return f"{driver}://{db.user}:{password}@{db.host}:{db.port}/{db.name}"
```
**Fix:** Read `driver` and `driver_async` from `db` config (added in Task 1.2):
```python
    driver = db.driver_async if async_driver else db.driver
```

**Current code (line 189):**
```python
    return f"redis://:{password}@{redis.host}:{redis.port}/{redis.db}"
```
**Fix:** Read `scheme` from redis config:
```python
    return f"{redis.scheme}://:{password}@{redis.host}:{redis.port}/{redis.db}"
```

**Current code (line 201):**
```python
    base_url = f"http://{server.host}:{server.port}"
```
**Fix:** Read `scheme` from server config (added in Task 1.1):
```python
    base_url = f"{server.scheme}://{server.host}:{server.port}"
```

**Verify:**
```bash
rg 'http://' modules/backend/core/config.py   # 0 matches
rg 'redis://' modules/backend/core/config.py  # 0 matches
rg 'postgresql' modules/backend/core/config.py # 0 matches (in URL construction)
```

### Task 5.3: Read `expire_on_commit` from config

**File:** `modules/backend/core/database.py`
**Current code (line 68):**
```python
            expire_on_commit=False,
```
**Fix:** Read from database config:
```python
    db_config = get_app_config().database
    ...
    expire_on_commit=db_config.expire_on_commit,
```

**Verify:**
```bash
rg 'expire_on_commit=False' modules/backend/core/database.py  # 0 matches
```

### Task 5.4: Fix pagination default inconsistency

**Audit ref:** #28
**File:** `modules/backend/core/pagination.py`
**Current code (line 144):**
```python
    limit: int = 20,
```
**Fix:** Read from `get_app_config().application.pagination.default_limit` — same as `get_pagination_params()` already does on line 43. Import the function and use its return value, or read the config directly.

**Verify:**
```bash
rg 'limit: int = 20' modules/backend/core/pagination.py  # 0 matches
```

### Task 5.5: Fix `dependencies.py` — use domain exception

**Audit ref:** #25
**File:** `modules/backend/core/dependencies.py`
**Current code (line 42):**
```python
    raise HTTPException(status_code=401, detail="Not authenticated")
```
**Fix:** Replace with:
```python
    from modules.backend.core.exceptions import AuthenticationError
    raise AuthenticationError("Not authenticated")
```
Remove the unused `HTTPException` import if no longer needed.

Also remove the dead `logger` import and instantiation (lines 13, 15) — **audit ref #65**.

**Verify:**
```bash
rg 'HTTPException' modules/backend/core/dependencies.py  # 0 matches (unless used elsewhere in file)
rg 'AuthenticationError' modules/backend/core/dependencies.py  # 1+ matches
```

### Task 5.6: Read `api_key_length` and `api_key_prefix` from config

**Audit ref:** #37
**File:** `modules/backend/core/security.py`
**Current code (lines 120-121):**
```python
    random_part = secrets.token_urlsafe(32)
    full_key = f"app_{random_part}"
```
**Fix:** Read from `get_app_config().security.api_keys.key_length` and `.prefix` (added in Task 1.4).

**Verify:**
```bash
rg 'token_urlsafe\(32\)' modules/backend/core/security.py   # 0 matches
rg '"app_"' modules/backend/core/security.py                 # 0 matches
```

### Task 5.7: Fix ambiguous exception chaining in security

**Audit ref:** #38
**File:** `modules/backend/core/security.py`
**Current code (lines 103-105):**
```python
    except JWTError as e:
        logger.warning("Token decode failed", extra={"error": str(e)})
        raise AuthenticationError("Invalid or expired token")
```
**Fix:** Add explicit `from None` (suppressing the original for security — don't leak JWT internals):
```python
        raise AuthenticationError("Invalid or expired token") from None
```

**Verify:**
```bash
rg 'from None' modules/backend/core/security.py  # 1 match
```

### Task 5.8: Read third-party log levels from config

**Audit ref:** #33
**File:** `modules/backend/core/logging.py`
**Current code (lines 210-211):**
```python
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
```
**Fix:** Read from `config["third_party_overrides"]` (added in Task 1.5) and loop:
```python
    for logger_name, level_str in config.get("third_party_overrides", {}).items():
        logging.getLogger(logger_name).setLevel(getattr(logging, level_str.upper()))
```

**Verify:**
```bash
rg 'uvicorn\.access' modules/backend/core/logging.py  # 0 matches (hardcoded name gone)
```

### Task 5.9: Read `VALID_SOURCES` from config

**Audit ref:** #32
**File:** `modules/backend/core/logging.py`
**Current code (lines 51-60):**
```python
VALID_SOURCES = frozenset({
    "web",
    "cli",
    ...
})
```
**Fix:** Load from logging config at module initialization. Replace the hardcoded frozenset with a function that reads from `logging.yaml` `valid_sources` (added in Task 1.6). Keep the `frozenset` type for immutability but populate it from config.

**Verify:**
```bash
rg '"web"' modules/backend/core/logging.py  # 0 matches (individual strings gone)
```

### Task 5.10: Add `structlog` context helpers to `core/logging.py`

**Audit ref:** #26, #27
**Why:** `middleware.py`, `cli.py`, `chat.py`, `tui.py` all `import structlog` directly for `contextvars.bind_contextvars()` and `clear_contextvars()`. Wrap these as public functions in the logging module.

**File:** `modules/backend/core/logging.py`
**Action:** Add two public functions:
```python
def bind_context(**kwargs: Any) -> None:
    """Bind key-value pairs to the structlog context for the current task."""
    structlog.contextvars.bind_contextvars(**kwargs)

def clear_context() -> None:
    """Clear all structlog context variables."""
    structlog.contextvars.clear_contextvars()
```

Then in **phase 6**, all files that `import structlog` directly will be updated to use these instead.

**Verify:**
```bash
rg 'def bind_context' modules/backend/core/logging.py   # 1 match
rg 'def clear_context' modules/backend/core/logging.py  # 1 match
```

### Task 5.11: Remove dead code in `exception_handlers.py`

**Audit ref:** #66
**File:** `modules/backend/core/exception_handlers.py`
**Action:** Remove the unused import `from pydantic import ValidationError as PydanticValidationError` (line 18).

**Verify:**
```bash
rg 'PydanticValidationError' modules/backend/core/exception_handlers.py  # 0 matches
```

### Task 5.12: Fix non-standard import in `utils.py`

**Audit ref:** #70
**File:** `modules/backend/core/utils.py`
**Current code (line 23):**
```python
    return datetime.fromtimestamp(
        __import__('time').time(), tz=timezone.utc
    ).replace(tzinfo=None)
```
**Fix:** Add `import time` at the top of the file. Replace `__import__('time').time()` with `time.time()`.

**Verify:**
```bash
rg '__import__' modules/backend/core/utils.py  # 0 matches
```

### Task 5.13: Fix `__init__.py` comment vs docstring

**Audit ref:** #71
**File:** `modules/backend/core/__init__.py`
**Current code:**
```python
# Core module - shared utilities, configuration, middleware
```
**Fix:** Change to:
```python
"""Core module — shared utilities, configuration, middleware."""
```

**Verify:**
```bash
rg '^#' modules/backend/core/__init__.py  # 0 matches
rg '"""' modules/backend/core/__init__.py # 1+ matches
```

**Commit phase 5.**

---

## Phase 6 — Entry File Fixes (cli.py, chat.py, tui.py)

### Task 6.1: Replace direct `structlog` imports with centralized logging

**Audit ref:** #26, #27
**Files:** `cli.py`, `chat.py`, `tui.py`

In each file:
1. Remove `import structlog`
2. Add `from modules.backend.core.logging import bind_context` (created in Task 5.10)
3. Replace all `structlog.contextvars.bind_contextvars(source="cli")` with `bind_context(source="cli")` (same for `"chat"`, `"tui"`)

**Verify:**
```bash
rg 'import structlog' cli.py chat.py tui.py  # 0 matches
```

### Task 6.2: Fix `chat.py` — remove dead import, add logging for errors

**Audit ref:** #69 (dead `get_logger` import), #54 (errors not logged)

**File:** `chat.py`
1. `get_logger` is imported (line 29) but never used. Either create a logger and use it, or remove the import. Since errors need to be logged (finding #54), **create a logger** `logger = get_logger(__name__)` and add `logger.error(...)` calls alongside the existing `click.echo()` error displays in the exception handlers.
2. Remove all `.get("key", "default")` fallback patterns (lines 65, 66, 131, 244, 283). Use direct key access `data["agent_name"]` etc. Let `KeyError` propagate for missing fields. **Audit ref #20.**

**Verify:**
```bash
rg '\.get\("agent_name"' chat.py  # 0 matches
rg '\.get\("output"' chat.py     # 0 matches
```

### Task 6.3: Fix `tui.py` — same patterns

**Audit ref:** #20, #54
**File:** `tui.py`
1. Remove `.get("key", "default")` fallback patterns (lines 256, 257). Use direct key access.
2. Add structured logging for caught exceptions (lines 286-291, 331-336). Import and use `get_logger`.

**Verify:**
```bash
rg '\.get\("agent_name"' tui.py  # 0 matches
```

### Task 6.4: Extract hardcoded API paths to config reads

**Audit ref:** #21
**Files:** `chat.py`, `tui.py`

**Current code examples:**
```python
"/api/v1/agents/chat"
"/api/v1/agents/chat/stream"
"/api/v1/agents/registry"
"/health/ready"
```

**Fix:** These files already call `get_app_config()` or `get_server_base_url()`. The `api_prefix` is available from `get_app_config().application.api_prefix`. Construct paths using that prefix:
```python
app_config = get_app_config()
prefix = app_config.application.api_prefix
chat_path = f"{prefix}/v1/agents/chat"
```

**Verify:**
```bash
rg '"/api/v1' chat.py tui.py  # 0 matches
```

### Task 6.5: Fix hardcoded `format_type="console"` overrides

**Audit ref:** #55
**Files:** `cli.py`, `chat.py`, `tui.py`

**Current code pattern:**
```python
    setup_logging(level="DEBUG", format_type="console")
```

**Fix:** This is an intentional override for CLI/TUI contexts where JSON output is unreadable. This is acceptable as-is since `setup_logging()` is designed to accept overrides. However, the format should come from a CLI-specific config. Add a `cli_format` key to `application.yaml` under a new `cli:` section:
```yaml
cli:
  log_format: "console"
```
Then read it: `format_type=get_app_config().application.cli.log_format`

If this is deemed too heavy, this task can be **deferred** — mark it as accepted-with-justification. The override mechanism is by design in `setup_logging()`.

### Task 6.6: Change mutable set to frozenset in `cli.py`

**Audit ref:** #72
**File:** `cli.py`
**Current code (line 32):**
```python
LONG_RUNNING_SERVICES = {"server", "worker", "scheduler", "telegram-poll"}
```
**Fix:** Change to `frozenset(...)`.

**Verify:**
```bash
rg 'frozenset' cli.py  # 1 match
```

**Commit phase 6.**

---

## Phase 7 — Remaining Backend & Telegram Fixes

### Task 7.1: Fix architecture layer violation in scheduled tasks

**Audit ref:** #9
**File:** `modules/backend/tasks/scheduled.py`
**Current code (lines 65-66):**
```python
    from modules.backend.api.health import check_database, check_redis
```
**Fix:** The health check functions (`check_database`, `check_redis`) perform actual health checks but live in the API layer. Move them to a service (e.g., `modules/backend/services/health.py`) and have both the API health endpoint and the scheduled task import from the service. Alternatively, create a thin service wrapper that the task calls, which in turn calls the existing functions. The API layer should also be updated to import from the service.

**Verify:**
```bash
rg 'from modules.backend.api.health' modules/backend/tasks/  # 0 matches
```

### Task 7.2: Move hardcoded pagination defaults to config reads

**Audit ref:** #53
**Files:**
- `modules/backend/repositories/base.py` (line 61: `limit: int = 50`)
- `modules/backend/repositories/note.py` (lines 30, 55, 80: `limit: int = 50`)
- `modules/backend/services/note.py` (lines 69, 89: `limit: int = 50` and `limit: int = 20`)
- `modules/backend/api/v1/endpoints/notes.py` (lines 96-100: `default=50, ge=1, le=100`)

**Fix:** In each file, import `get_app_config` and read `pagination.default_limit` and `pagination.max_limit` from `application.yaml`. The `limit: int = 20` in service line 89 is an inconsistency that must also use the config value.

**Verify:**
```bash
rg 'limit: int = 50' modules/backend/repositories/ modules/backend/services/  # 0 matches
rg 'limit: int = 20' modules/backend/services/note.py                        # 0 matches
```

### Task 7.3: Consolidate rate limiting into a single shared utility

**Audit ref:** #24
**Files:**
- `modules/backend/gateway/security/rate_limiter.py` — `GatewayRateLimiter`
- `modules/telegram/middlewares/rate_limit.py` — `RateLimitMiddleware`
- `modules/telegram/services/notifications.py` — `_check_rate_limit` method

**Fix:** Create a shared rate limiting utility in `modules/backend/core/rate_limit.py` (or similar) that implements the sliding-window algorithm once. Refactor all three consumers to use this shared implementation, passing their specific config (window size, max count) from their respective YAML configs.

**Verify:**
```bash
# The shared module should exist:
test -f modules/backend/core/rate_limit.py && echo "OK"
# Each consumer should import from it:
rg 'from modules.backend.core.rate_limit' modules/backend/gateway/security/rate_limiter.py
rg 'from modules.backend.core.rate_limit' modules/telegram/middlewares/rate_limit.py
rg 'from modules.backend.core.rate_limit' modules/telegram/services/notifications.py
```

### Task 7.4: Fix hardcoded values in telegram modules

**Audit ref:** #45, #47, #48
- `modules/telegram/middlewares/auth.py:19-23` — `USER_ROLES` dict hardcoded. Move to `application.yaml` under `telegram.roles` or similar.
- `modules/telegram/services/notifications.py:39` — `RATE_LIMIT_WINDOW = 60`. Read from `security.yaml` `rate_limiting.telegram.messages_per_minute` (window = 60 is implicit from "per minute").
- `modules/backend/gateway/adapters/telegram.py:20` — `TELEGRAM_MAX_MESSAGE_LENGTH = 4096`. Add to `application.yaml` under `telegram.max_message_length`.

**Verify:**
```bash
rg 'USER_ROLES = \{' modules/telegram/middlewares/auth.py           # 0 matches
rg 'RATE_LIMIT_WINDOW = 60' modules/telegram/services/notifications.py  # 0 matches
rg '4096' modules/backend/gateway/adapters/telegram.py                  # 0 matches
```

### Task 7.5: Fix `require_role` missing `functools.wraps`

**Audit ref:** #46
**File:** `modules/telegram/middlewares/auth.py`
**Current code (line 154):**
```python
        async def wrapper(*args, **kwargs):
```
**Fix:** Add `@functools.wraps(func)` decorator above the `wrapper` function. Add `import functools` at the top of the file.

**Verify:**
```bash
rg 'functools.wraps' modules/telegram/middlewares/auth.py  # 1 match
```

### Task 7.6: Fix `SCHEDULED_TASKS` to read from config

**Audit ref:** #49
**File:** `modules/backend/tasks/scheduled.py`
**Current code (lines 142-168):** Entire `SCHEDULED_TASKS` dict is hardcoded.
**Fix:** Read from `config/settings/tasks.yaml` (created in Task 1.7). Load the scheduled task config using `load_yaml_config("tasks.yaml")` and construct the dict from it. Keep the function references in code (they must be), but read cron schedules, retry settings, and kwargs from config.

**Verify:**
```bash
rg '"0 2 \*' modules/backend/tasks/scheduled.py  # 0 matches (cron from config now)
```

### Task 7.7: Fix `filesystem.py` — raise instead of returning error string

**Audit ref:** #43
**File:** `modules/backend/agents/tools/filesystem.py`
**Current code (line 29):**
```python
        return f"Error: file not found: {file_path}"
```
**Fix:** This is a PydanticAI tool function where the return value goes to the LLM. In this context, returning a string is actually the correct pattern for tool functions (the LLM needs to see the error). **Reclassify as accepted-by-design.** No change needed here.

### Task 7.8: Fix hardcoded subprocess in `tools/code.py`

**Audit ref:** #30
**File:** `modules/backend/agents/tools/code.py`
**Current code (lines 63-66):**
```python
        [sys.executable, "-m", "pytest", "tests/unit", "-v", "--tb=short"],
```
**Fix:** Read test directory and flags from agent config. Add `test_command` settings to `config/agents/code/qa/agent.yaml`:
```yaml
test_command:
  directory: "tests/unit"
  flags: ["-v", "--tb=short"]
  tail_lines: 50
```
Read these in the tool function.

**Verify:**
```bash
rg 'tests/unit.*--tb=short' modules/backend/agents/tools/code.py  # 0 matches
```

### Task 7.9: Fix self-referential import in `bot.py`

**Audit ref:** #74
**File:** `modules/telegram/bot.py`
**Current code (line 125):**
```python
    from modules.telegram.bot import get_dispatcher
```
**Fix:** Replace with a direct call to `get_dispatcher()` since it's already in the same module.

**Verify:**
```bash
rg 'from modules.telegram.bot import' modules/telegram/bot.py  # 0 matches
```

### Task 7.10: Fix repeated inline `import re` in telegram adapter

**Audit ref:** #73
**File:** `modules/backend/gateway/adapters/telegram.py`
**Current code (lines 100, 104, 110):** `import re` appears inside three functions.
**Fix:** Move `import re` to the top of the file. Remove the three inline imports.

**Verify:**
```bash
rg -c 'import re' modules/backend/gateway/adapters/telegram.py  # should be 1
```

### Task 7.11: Fix hardcoded values in `tasks/example.py`

**Audit ref:** #50, #51
**File:** `modules/backend/tasks/example.py`
- Line 162: `file_path=f"/reports/{report_id}.pdf"` — hardcoded path. Read reports directory from config.
- Lines 215-236: `TASK_CONFIG` dict defined but never referenced — **dead code, remove it**.

**Verify:**
```bash
rg 'TASK_CONFIG' modules/backend/tasks/example.py     # 0 matches
rg '/reports/' modules/backend/tasks/example.py       # 0 matches
```

### Task 7.12: Fix `os.environ.get` with fallback in `tests/conftest.py`

**Audit ref:** #56
**File:** `tests/conftest.py`
**Current code (lines 63-66):**
```python
    return os.environ.get(
        "TEST_DATABASE_URL",
        "sqlite+aiosqlite:///:memory:",
    )
```
**Fix:** This is a test configuration convenience. The fallback to SQLite in-memory for tests is a legitimate pattern — tests should work without external setup. **Reclassify as accepted-by-design for test infrastructure.** No change needed.

**Commit phase 7.**

---

## Phase 8 — Dead Code Cleanup

### Task 8.1: Remove dead code in coordinator

**Audit ref:** #67, #68
**File:** `modules/backend/agents/coordinator/coordinator.py`
- Line 23: Remove unused `from functools import lru_cache` import (if it's no longer used after phase 4 refactoring — verify first).
- Line 190: Remove the dead `usage = {}` variable.

**Verify:**
```bash
python -c "import ast; ast.parse(open('modules/backend/agents/coordinator/coordinator.py').read())"  # no syntax errors
```

### Task 8.2: Remove dead code in telegram modules

**Audit ref:** #61, #62, #63, #64
- `modules/telegram/states/example.py:23-50` — Remove `SettingsForm` and `RegistrationForm` if truly unused. Search the codebase first to confirm.
- `modules/telegram/callbacks/common.py:92-116` — Remove `ItemCallback` if unused.
- `modules/telegram/keyboards/common.py:150-196` — Remove `get_yes_no_keyboard()` and `get_back_keyboard()` if unused.
- `modules/telegram/middlewares/rate_limit.py:157-208` — Remove `ThrottleMiddleware` class if unused.

**Before removing each item, verify it's truly unused:**
```bash
rg 'SettingsForm' modules/ --type py
rg 'RegistrationForm' modules/ --type py
rg 'ItemCallback' modules/ --type py
rg 'get_yes_no_keyboard' modules/ --type py
rg 'get_back_keyboard' modules/ --type py
rg 'ThrottleMiddleware' modules/ --type py
```

Only remove if the search returns only the definition and no usages.

### Task 8.3: Remove dead `TASK_CONFIG` from example tasks

**Audit ref:** #50
**File:** `modules/backend/tasks/example.py`
Already covered in Task 7.11. Verify it was removed.

**Commit phase 8.**

---

## Phase 9 — Verification

### Task 9.1: Run the compliance checker

```bash
python scripts/compliance_checker.py --verbose
```

All violations detected by the scanner should be reduced. Any remaining findings need investigation.

### Task 9.2: Run full grep sweeps

Run these and confirm 0 results for each:

```bash
# No hardcoded fallback model names
rg 'claude-haiku' modules/ --type py

# No direct structlog imports outside core/logging.py
rg 'import structlog' modules/ cli.py chat.py tui.py --type py | rg -v 'core/logging.py'

# No direct import logging outside core/logging.py
rg '^import logging' modules/ scripts/ --type py | rg -v 'core/logging.py'

# No datetime.now() or datetime.utcnow()
rg 'datetime\.(now|utcnow)\(\)' modules/ scripts/ --type py

# No bare except:
rg 'except:' modules/ scripts/ --type py

# No print() in modules/
rg 'print\(' modules/ --type py

# No relative imports in modules/
rg 'from \.' modules/ --type py
```

### Task 9.3: Run existing tests

```bash
python -m pytest tests/unit -v --tb=short
```

All tests must pass. If any fail due to the refactoring, fix them before committing.

### Task 9.4: Syntax-check all modified files

```bash
python -m py_compile cli.py
python -m py_compile chat.py
python -m py_compile tui.py
python -m py_compile scripts/dead_code_detector.py
python -m py_compile scripts/compliance_checker.py
find modules/ -name "*.py" -exec python -m py_compile {} +
```

**Final commit phase 9 if any fixes were needed during verification.**

---

## Deferred / Accepted-by-Design

These findings were reviewed and intentionally excluded from this plan:

| # | Finding | Reason |
|---|---------|--------|
| 7.7 | `filesystem.py` returns error string | PydanticAI tool pattern — LLM needs to see the error as a string return |
| 7.12 | `tests/conftest.py` fallback to SQLite | Legitimate test infrastructure pattern — tests must work without external DB |
| 6.5 | `format_type="console"` in entry files | `setup_logging()` is designed for overrides; could be config-driven later |
| 58 | Global lazy singletons (broker, scheduler, etc.) | Common Python pattern for expensive resources; would need a factory/DI overhaul |
| 60 | Missing test coverage for 16 modules | Separate effort — tracked but out of scope for this remediation |

---

## Summary of Changes by Phase

| Phase | Description | Findings Addressed |
|-------|-------------|--------------------|
| 0 | Git preparation | — |
| 1 | YAML config extensions | Prerequisites for #22, #31, #32, #33, #37, #49 |
| 2 | P8 security fix | #1, #2 |
| 3 | dead_code_detector rewrite | #13, #14, #15, #16, #17, #18, #19 |
| 4 | Agent system fallbacks | #3, #4, #5, #6, #7, #8, #10, #11, #12, #29, #40, #41, #42, #44 |
| 5 | Core module fixes | #22, #23, #25, #26, #27, #28, #31, #32, #33, #37, #38, #65, #66, #70, #71 |
| 6 | Entry file standardization | #20, #21, #27, #54, #55, #69, #72 |
| 7 | Backend/telegram fixes | #9, #24, #30, #45, #46, #47, #48, #49, #50, #51, #53, #73, #74 |
| 8 | Dead code cleanup | #50, #61, #62, #63, #64, #67, #68 |
| 9 | Verification | All |
