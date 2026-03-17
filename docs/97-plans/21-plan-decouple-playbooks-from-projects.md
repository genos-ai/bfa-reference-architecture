# Implementation Plan: Decouple Playbooks from Projects

*Created: 2026-03-13*
*Status: Ready*
*Depends on: Plan 17 (Playbooks & Missions), Plan 18 (Project Context Layer)*
*Blocked by: Nothing*

---

## Summary

Remove the static `project_id` from playbook YAML files. Playbooks become reusable recipes that target any project at runtime via `--project <name>`. Projects are resolved by **name** (get-or-create), not by hardcoded UUID. The `db clear` command is updated to preserve projects and PCD by default, since these are infrastructure — not ephemeral run data.

**Why:** The current design hardcodes a UUID in each playbook YAML, coupling one playbook to one project. This means:
- The same audit playbook can't run against different projects without duplicating the YAML
- `db clear` breaks the FK mapping (project row deleted, playbook YAML still references it)
- UUIDs in YAML are non-portable across environments (dev/staging/prod)
- YAML files become a source of state rather than pure configuration

**After this change:**
```bash
# Same playbook, different projects
python cli.py playbook run system.platform-audit --project my-saas-app
python cli.py playbook run system.platform-audit --project my-library
python cli.py playbook run code.architecture-review --project my-saas-app

# First run auto-creates the project; subsequent runs accumulate history
```

**Dev mode: breaking changes allowed.** This modifies the playbook YAML schema, which is an internal format with no external consumers.

---

## Context

- Plan 17: `docs/97-plans/17-plan-playbooks-missions.md` — original playbook design, defines `project_id` as a top-level field
- Plan 18: `docs/97-plans/18-plan-project-context-layer.md` — project context layer, PCD, history queries
- Playbook schema: `modules/backend/schemas/playbook.py` — PlaybookSchema with mandatory `project_id`
- Playbook runner: `modules/backend/services/playbook_run.py` — resolves project_id, creates PlaybookRun
- Project service: `modules/backend/services/project.py` — `create_project()`, `get_project()`, `get_project_by_name()`
- Project model: `modules/backend/models/project.py` — `Project` with unique `name` column
- CLI playbook: `modules/backend/cli/playbook.py` — `--project` flag handling
- CLI db: `modules/backend/cli/db.py` — `db clear`, `db clear-missions`
- Existing playbooks: `config/playbooks/*.yaml` — all have `project_id` and `project_name`
- Tests: `tests/unit/backend/services/test_project_id_threading.py` — tests for project_id flow
- Principles: P4 (Scope Is Configuration Not Code), P2 (Deterministic Over Non-Deterministic)

---

## Design Decisions

### D1: Project resolution by name, not UUID

Playbook YAML loses `project_id`. The `--project` CLI flag accepts a **project name** (human-readable slug). At runtime, the playbook runner resolves the name to a UUID via get-or-create:

```
--project my-app  →  SELECT * FROM projects WHERE name = 'my-app'
                     If not found → INSERT INTO projects (name, ...) VALUES ('my-app', ...)
                     Return project.id (UUID)
```

**Rationale:** Names are portable (same in dev/staging/prod), human-readable, and deterministic. UUIDs are internal identifiers that should never appear in configuration files.

### D2: `--project` is required for playbook runs

If `--project` is not provided, the CLI errors with a clear message. No default project, no fallback. This makes the project scope explicit and avoids accidental history pollution.

**Exception:** Ad-hoc missions (`cli.py mission run`) remain project-optional for quick one-off tasks.

### D3: `db clear` preserves projects and PCD by default

Projects and their PCD are infrastructure — they accumulate context across many runs and are expensive to recreate. `db clear` should only clear run data (missions, playbook runs, task executions, sessions). A new `--include-projects` flag enables full nuclear reset when needed.

### D4: Remove `_ensure_project` band-aid

The `_ensure_project` method added to `PlaybookRunService` was a workaround for the hardcoded UUID problem. With name-based resolution via get-or-create, it's replaced by a cleaner `_resolve_project()` method.

---

## Scope

### In scope
- Remove `project_id` from playbook YAML schema
- Add `--project <name>` as required CLI argument for `playbook run`
- Implement name-based project resolution (get-or-create) in PlaybookRunService
- Update `db clear` to preserve projects/PCD by default
- Update all playbook YAML files
- Inject project context (PCD + recent failures) into the Planning Agent prompt
- Update tests

### Out of scope
- API endpoint changes (playbook API is not yet project-aware; future work)
- Project management CLI (create/list/delete projects — exists already)
- Scheduled trigger changes (Temporal integration handles project_id separately)

---

## Implementation Steps

### Step 1: Update PlaybookSchema — remove `project_id`, keep `project_name` optional

**File:** `modules/backend/schemas/playbook.py`

**Changes:**
1. Remove the `project_id` field (currently lines 151-155):
   ```python
   # REMOVE this entire field:
   project_id: str = Field(
       ...,
       min_length=1,
       description="Project UUID to associate with all runs spawned by this playbook.",
   )
   ```

2. Keep `project_name` but make it purely informational (already optional, no change needed):
   ```python
   project_name: str | None = Field(
       None,
       description="Human-readable project name (display only).",
   )
   ```

**Verification:** Schema validation tests must pass without `project_id` in test fixtures.

---

### Step 2: Update playbook YAML files — remove `project_id`

**Files:**
- `config/playbooks/code.architecture-review.playbook.yaml`
- `config/playbooks/system.platform-audit.playbook.yaml`
- `config/playbooks/examples/research.news-digest.playbook.yaml`

**Changes for each file:**
1. Delete the `project_id: "..."` line
2. Keep `project_name` if present (it's display-only metadata)

**Example before:**
```yaml
project_id: "d4bb2073-d86a-465b-805f-9400d4c2449d"
project_name: "system-audit-and-health-check"
```

**Example after:**
```yaml
project_name: "system-audit-and-health-check"
```

---

### Step 3: Update PlaybookRunService — replace `_ensure_project` with `_resolve_project`

**File:** `modules/backend/services/playbook_run.py`

**3a. Update `run_playbook()` signature and project resolution (around lines 84-90):**

Replace the current logic:
```python
# REMOVE:
if not project_id:
    project_id = playbook.project_id

if project_id:
    await self._ensure_project(project_id, playbook)
```

With name-based resolution:
```python
# project_name is now required (passed from CLI --project flag)
if not project_name:
    raise ValueError(
        "Project name is required. Use --project <name> to specify the target project."
    )

project_id = await self._resolve_project(project_name, playbook)
```

The `run_playbook()` method signature changes:
```python
async def run_playbook(
    self,
    playbook_name: str,
    triggered_by: str = "user:cli",
    context_overrides: dict[str, Any] | None = None,
    on_progress: Any | None = None,
    project_name: str | None = None,    # CHANGED: was project_id: str | None
) -> PlaybookRun:
```

**3b. Replace `_ensure_project()` with `_resolve_project()`:**

Delete the existing `_ensure_project` method and replace with:

```python
async def _resolve_project(
    self,
    project_name: str,
    playbook: PlaybookSchema,
) -> str:
    """Resolve a project name to a UUID, creating the project if needed.

    Returns the project UUID.
    """
    from modules.backend.services.project import ProjectService

    project_service = ProjectService(self._session)
    project = await project_service.get_project_by_name(project_name)

    if project:
        return project.id

    # Auto-create project from name
    project = await project_service.create_project(
        name=project_name,
        description=f"Auto-created for playbook: {playbook.description[:200]}",
        owner_id="system:playbook",
    )
    await self._session.commit()
    logger.info(
        "Auto-created project",
        extra={"project_name": project_name, "project_id": project.id},
    )
    return project.id
```

**Key difference from `_ensure_project`:**
- Takes a **name**, not a UUID
- Uses `get_project_by_name()` (already exists in ProjectService)
- No hardcoded UUID — the DB generates the UUID
- Returns the UUID for downstream use

---

### Step 4: Update CLI playbook commands — `--project` accepts name

**File:** `modules/backend/cli/playbook.py`

**4a. Update the `--project` option:**

Find where `--project` is defined as a CLI option and change it from accepting a UUID to accepting a name string. The option should be **required** for the `run` subcommand.

Current (approximate):
```python
@click.option("--project", default=None, help="Project UUID")
```

Change to:
```python
@click.option("--project", required=True, help="Project name to run against (created if new)")
```

**4b. Update `_action_run()` to pass `project_name`:**

Change the call from:
```python
await run_service.run_playbook(
    playbook_name=playbook_name,
    project_id=project_id,  # was UUID
    ...
)
```
To:
```python
await run_service.run_playbook(
    playbook_name=playbook_name,
    project_name=project,  # now a name
    ...
)
```

**4c. Update `run_playbook_cli()` (the top-level handler):**

Similarly rename `project_id` parameter to `project_name` and pass through.

---

### Step 5: Update `db clear` — preserve projects by default

**File:** `modules/backend/cli/db.py`

**5a. Split `ALL_TABLES` into two groups:**

```python
# Infrastructure tables — preserved by default
PROJECT_TABLES = [
    "milestone_summaries",
    "project_decisions",
    "context_changes",
    "project_contexts",
    "project_members",
    "projects",
]

# Run data tables — cleared by db clear
RUN_TABLES = [
    "mission_decisions",
    "task_attempts",
    "task_executions",
    "mission_records",
    "session_messages",
    "session_channels",
    "missions",
    "playbook_runs",
    "sessions",
    "notes",
]

ALL_TABLES = RUN_TABLES + PROJECT_TABLES
```

**5b. Update `_action_clear()` to default to RUN_TABLES:**

```python
async def _action_clear(cli_logger, *, table, limit, confirm):
    """Clear run data. Use --include-projects for full reset."""
    tables = ALL_TABLES if include_projects else RUN_TABLES
    # ... truncate tables
```

**5c. Add `--include-projects` flag to the `clear` command:**

```python
@click.option("--include-projects", is_flag=True, default=False,
              help="Also clear projects and PCD (full nuclear reset)")
```

**5d. Update the confirmation message** to reflect what will be cleared:

```python
if include_projects:
    click.echo("This will DELETE ALL DATA including projects and context.")
else:
    click.echo("This will DELETE run data (missions, sessions, playbook runs).")
    click.echo("Projects and PCD are preserved. Use --include-projects for full reset.")
```

---

### Step 6: Remove `project_id` parameter from ProjectService.create_project()

**File:** `modules/backend/services/project.py`

The `project_id` parameter was added as part of the `_ensure_project` band-aid. Remove it since projects now get auto-generated UUIDs:

```python
async def create_project(
    self,
    *,
    # REMOVE: project_id: str | None = None,
    name: str,
    description: str,
    owner_id: str,
    ...
) -> Project:
```

Also revert the `create_kwargs["id"] = project_id` logic back to the simpler direct call:

```python
project = await self._project_repo.create(
    name=name,
    description=description,
    owner_id=owner_id,
    ...
)
```

---

### Step 7: Update tests

**7a. Update `test_project_id_threading.py`:**

The existing tests verify CLI UUID override > YAML UUID precedence. Replace with:

- `test_run_playbook_resolves_project_by_name()` — verifies that `--project my-app` creates the project and assigns its UUID to the PlaybookRun
- `test_run_playbook_reuses_existing_project()` — verifies that running twice with `--project my-app` uses the same project UUID
- `test_run_playbook_requires_project_name()` — verifies that omitting `--project` raises an error

**7b. Update `test_playbook_schema.py`:**

Remove `project_id` from `_minimal_playbook()` helper and any tests that assert on it.

**7c. Update `test_playbook_service.py`:**

Remove `project_id` from playbook fixtures and assertions.

**7d. Update any integration tests** that reference playbook `project_id`:

Search for `project_id` in `tests/` files that reference playbook context and update accordingly.

---

### Step 8: Update PlaybookService.generate_mission_briefs()

**File:** `modules/backend/services/playbook.py`

Check if `generate_mission_briefs()` or any other PlaybookService method references `playbook.project_id`. If so, remove those references since project_id now comes from the resolved project at runtime, not from the playbook YAML.

The method at approximately line 200+ generates mission brief dicts. If it includes `project_id` from the playbook, remove that key — it will be injected by the PlaybookRunService after project resolution.

---

### Step 9: Inject project context into the Planning Agent

**Why this matters:** Today the Planning Agent is blind to the project. Context services are created *after* planning (line 479 of `mission_control.py`), so the planner decomposes missions without knowing the project's architecture, past failures, or codebase structure. For Tier 4/5 autonomous agents running for days or weeks, this means:

- **Blind decomposition** — the planner doesn't know the codebase has 200 files in a monorepo, so it can't size tasks correctly
- **Repeated failures** — if the same playbook ran last week and an agent hit a token limit on a large module, the planner doesn't know to split that module into sub-tasks
- **Wasted re-planning** — when a Temporal workflow retries after approval, `handle_mission()` calls the planner fresh, but the planner still doesn't see the PCD that was enriched by the failed first run's `context_updates`

**Files:**
- `modules/backend/agents/mission_control/mission_control.py`
- `modules/backend/agents/mission_control/helpers.py`

**9a. Move context service creation before planning in `handle_mission()`:**

Currently (lines 476-490 of `mission_control.py`), context services are created after planning:

```python
# CURRENT ORDER (wrong for planning):
planning_prompt = _build_planning_prompt(...)    # line 418
plan = _call_planning_agent(planning_prompt)      # line 432
# ... planning loop ...
if project_id and db_session:                     # line 479 — TOO LATE
    pcd_manager = ProjectContextManager(db_session)
    context_curator = ContextCurator(pcd_manager)
    ...
```

Move context service creation **before** the planning prompt is built:

```python
# NEW ORDER:
roster = load_roster(roster_name)
roster_description = _build_roster_prompt(roster)

# 1. Create context services FIRST (if project is set)
context_curator = None
context_assembler = None
project_context = None
recent_failures = None

if project_id and db_session:
    pcd_manager = ProjectContextManager(db_session)
    context_curator = ContextCurator(pcd_manager)
    history_service = HistoryQueryService(db_session)

    from modules.backend.core.config import find_project_root
    from modules.backend.services.code_map.loader import CodeMapLoader

    code_map_loader = CodeMapLoader(find_project_root())
    context_assembler = ContextAssembler(
        context_manager=pcd_manager,
        history_service=history_service,
        code_map_loader=code_map_loader,
    )

    # Load project context for the planner
    try:
        project_context = await context_curator.get_project_context(project_id)
    except (OSError, ValueError, RuntimeError):
        logger.warning(
            "Failed to load PCD for planning (non-fatal)",
            extra={"project_id": project_id},
            exc_info=True,
        )

    # Load recent failures so the planner can avoid repeating them
    try:
        recent_failures = await history_service.get_recent_failures(
            project_id, limit=5,
        )
    except (OSError, ValueError, RuntimeError):
        logger.warning(
            "Failed to load failure history for planning (non-fatal)",
            extra={"project_id": project_id},
            exc_info=True,
        )

# 2. Build planning prompt WITH project context
planning_prompt = _build_planning_prompt(
    mission_brief=mission_brief,
    mission_id=mission_id,
    roster_description=roster_description,
    upstream_context=upstream_context,
    project_context=project_context,       # NEW
    recent_failures=recent_failures,       # NEW
)

# 3. Call Planning Agent (same loop as before)
# ...

# 4. Execute dispatch loop (context_curator and context_assembler already created above)
outcome = await dispatch(
    plan=plan,
    roster=roster,
    execute_agent_fn=_make_agent_executor(session_service, event_bus),
    mission_budget_usd=mission_budget_usd,
    project_id=project_id,
    context_curator=context_curator,       # reused from above
    context_assembler=context_assembler,   # reused from above
)
```

**9b. Update `_build_planning_prompt()` to include project context:**

**File:** `modules/backend/agents/mission_control/helpers.py`

Add two new optional parameters and render them as prompt sections:

```python
def _build_planning_prompt(
    mission_brief: str,
    mission_id: str,
    roster_description: str,
    upstream_context: dict | None,
    code_map: dict | None = None,
    project_context: dict | None = None,    # NEW
    recent_failures: list | None = None,    # NEW
) -> str:
    """Assemble the full prompt for the Planning Agent."""
    parts = [
        f"## Mission Brief\n\n{mission_brief}\n",
        f"## Mission ID\n\n{mission_id}\n",
        roster_description,
    ]

    # NEW: Project context (PCD) — gives planner project awareness
    if project_context:
        parts.append(
            "## Project Context\n\n"
            "The following is the Project Context Document (PCD) for the target project. "
            "Use it to understand the project's architecture, constraints, current state, "
            "and key decisions when decomposing tasks.\n\n"
            f"```json\n{json.dumps(project_context, indent=2)}\n```\n"
        )

    # NEW: Recent failures — planner should avoid repeating them
    if recent_failures:
        parts.append(
            "## Recent Failures (Avoid Repeating)\n\n"
            "The following tasks failed in recent runs against this project. "
            "Account for these when planning — e.g., split large modules that "
            "caused token limits, avoid approaches that timed out, adjust task "
            "granularity based on past outcomes.\n\n"
            f"```json\n{json.dumps(recent_failures, indent=2)}\n```\n"
        )

    if upstream_context:
        # ... (unchanged)

    if code_map:
        # ... (unchanged)

    parts.append(
        "## Output Format\n\n"
        "Return your task plan as JSON within <task_plan> tags.\n"
        "Follow the TaskPlan schema exactly. See system prompt for rules.\n"
    )

    return "\n".join(parts)
```

**9c. Update `_call_planning_agent()` to pass context through:**

If `_call_planning_agent()` also constructs `PlanningAgentDeps`, add `project_context` and `recent_failures` to the deps dataclass so the Planning Agent's system prompt can reference them if needed.

**Key behavior:**
- Both `project_context` and `recent_failures` are **non-fatal** — if loading fails, planning proceeds without them (same as before)
- The planner gets the PCD as a read-only context section, not as a mutable input
- Context services are created once and reused for both planning and dispatch (no duplicate DB queries)

**Verification:** After implementing, run a playbook twice against the same project. On the second run, confirm that the Planning Agent's prompt includes the PCD and any failures from the first run by checking structured logs for the planning prompt length increase.

---

## File Change Summary

| File | Change | Type |
|------|--------|------|
| `modules/backend/schemas/playbook.py` | Remove `project_id` field from PlaybookSchema | Breaking schema change |
| `config/playbooks/code.architecture-review.playbook.yaml` | Remove `project_id` line | Config |
| `config/playbooks/system.platform-audit.playbook.yaml` | Remove `project_id` line | Config |
| `config/playbooks/examples/research.news-digest.playbook.yaml` | Remove `project_id` line | Config |
| `modules/backend/services/playbook_run.py` | Replace `_ensure_project` with `_resolve_project`; change parameter from `project_id` to `project_name` | Service |
| `modules/backend/services/project.py` | Remove `project_id` parameter from `create_project()` | Service |
| `modules/backend/cli/playbook.py` | Make `--project` required, accept name not UUID | CLI |
| `modules/backend/cli/db.py` | Split tables, add `--include-projects` flag, default to preserving projects | CLI |
| `modules/backend/services/playbook.py` | Remove `project_id` from `generate_mission_briefs()` if present | Service |
| `modules/backend/agents/mission_control/mission_control.py` | Move context service creation before planning; pass PCD + failures to planner | Orchestration |
| `modules/backend/agents/mission_control/helpers.py` | Add `project_context` and `recent_failures` params to `_build_planning_prompt()` | Orchestration |
| `tests/unit/backend/schemas/test_playbook_schema.py` | Remove `project_id` from fixtures | Test |
| `tests/unit/backend/services/test_project_id_threading.py` | Rewrite tests for name-based resolution | Test |
| `tests/unit/backend/services/test_playbook_service.py` | Remove `project_id` from fixtures | Test |

---

## Validation Checklist

After implementation, verify:

1. `python cli.py playbook run system.platform-audit --project my-test-project` succeeds
   - Project `my-test-project` auto-created on first run
   - Second run reuses the same project (same UUID)
2. `python cli.py playbook run system.platform-audit` without `--project` shows a clear error
3. `python cli.py db clear --yes` clears runs but preserves projects
4. `python cli.py db clear --yes --include-projects` clears everything
5. `python cli.py context assembled --project <uuid>` shows Layer 2 history from the run
6. All unit tests pass: `python -m pytest tests/unit/ -q`
7. Playbook YAML files have no `project_id` field
8. Running the same playbook against two different `--project` names creates two separate projects with independent history
9. On the second playbook run against the same project, the Planning Agent's prompt includes PCD and recent failure history from the first run (verify via structured logs or prompt length increase)
10. If PCD or history loading fails, planning proceeds without them (graceful degradation — no crash)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Project name collisions across users | `name` column is already UNIQUE in the projects table; first creator wins |
| Existing DB has projects with UUIDs referenced elsewhere | `ondelete="SET NULL"` on FK constraints means old references degrade gracefully |
| API endpoints still accept `project_id` UUID | Out of scope; API layer can be updated separately when needed |
| Temporal workflow `MissionWorkflowInput` has `project_id` | No change needed — Temporal receives the resolved UUID from the mission, not from the playbook |
| PCD + failures add tokens to planning prompt | PCD is capped at 20KB (~5K tokens); failures limited to 5 entries. Combined overhead ~6-8K tokens — within the Planning Agent's 16K max_tokens budget. Truncate PCD summary if needed |
| Planning Agent ignores project context | Advisory only — worst case the planner produces the same plan it would have without it. No regression risk |
