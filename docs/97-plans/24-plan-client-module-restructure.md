# Plan 24 — Client Module Restructure

**Status:** Completed
**Created:** 2026-03-18
**Depends on:** None (prerequisite for Plan 23 TUI)
**Blocks:** Plan 23 (TUI Mission Control Dashboard)

## Objective

Group all Python client surfaces (CLI, TUI, Telegram) under `modules/clients/` with a shared `common/` module, and remove client code from `modules/backend/`.

The CLI currently lives inside `modules/backend/cli/` — a client surface buried in the backend package. The TUI skeleton is at `modules/tui/`. Telegram is at `modules/telegram/`. All three are Python clients that import from `modules.backend.services`, `modules.backend.agents`, and `modules.backend.core`. They should be peers under a single `clients/` namespace with shared infrastructure.

---

## Current Structure (Problem)

```
modules/
├── backend/
│   ├── cli/              ← Client surface inside backend (wrong layer)
│   │   ├── report.py     ← 867 lines, display primitives mixed with AI narrative
│   │   ├── gate.py       ← Gate reviewer with reusable helpers (_cost_color, _status_icon)
│   │   ├── mission.py    ← 510 lines
│   │   └── ... (21 files, 4,106 lines total)
│   ├── services/         ← Actual backend
│   ├── agents/           ← Actual backend
│   └── ...
├── frontend/             ← JS/React (different ecosystem, stays here)
├── telegram/             ← Python client, isolated
└── tui/                  ← Python client, isolated (skeleton only)
```

**Problems:**
1. CLI is in `backend/` but it's a client — violates layer separation
2. `report.py` (867 lines) mixes reusable display primitives with CLI-specific AI narrative — exceeds 500-line rule
3. Gate helpers (`_cost_color`, `_status_icon`) in CLI will be duplicated by TUI
4. No shared client infrastructure — each client reinvents service access patterns
5. `modules.backend.agents.mission_control.gate` imports from `modules.backend.cli.gate` — backend depending on a client (circular layer violation)

---

## Target Structure

```
modules/
├── backend/                        # Pure business logic — no UI code
│   ├── agents/
│   ├── services/
│   ├── events/
│   ├── schemas/
│   ├── core/
│   ├── models/
│   ├── api/                        # REST API (server interface, stays)
│   └── ...                         # No cli/ directory
├── clients/                        # All Python client surfaces
│   ├── __init__.py
│   ├── common/                     # Shared client infrastructure
│   │   ├── __init__.py
│   │   ├── display.py              # 219 lines — Rich primitives (keyword-only APIs)
│   │   └── gate_helpers.py         # 51 lines — cost_color, status_icon, gate header
│   ├── cli/                        # Click commands (moved from backend/cli/)
│   │   ├── __init__.py
│   │   ├── report.py               # 638 lines — AI narrative + render_human + re-exports from common.display
│   │   ├── gate.py                 # CliGateReviewer (imports from common.gate_helpers + common.display)
│   │   ├── mission.py
│   │   ├── playbook.py
│   │   ├── project.py
│   │   ├── context.py
│   │   ├── agent.py
│   │   ├── db.py
│   │   ├── helpers.py
│   │   └── ... (all existing CLI files)
│   ├── tui/                        # Textual TUI (moved from modules/tui/)
│   │   ├── app.py
│   │   ├── services/
│   │   ├── widgets/
│   │   ├── screens/
│   │   └── styles/
│   └── telegram/                   # Telegram bot (moved from modules/telegram/)
│       ├── bot.py
│       ├── handlers/
│       ├── callbacks/
│       ├── keyboards/
│       ├── middlewares/
│       ├── services/
│       └── states/
├── frontend/                       # JS/React — stays (different ecosystem)
```

---

## What Moves Where

### Move 1: CLI (`modules/backend/cli/` → `modules/clients/cli/`)

All 21 files move. Import path changes from `modules.backend.cli.*` to `modules.clients.cli.*`.

**Files (4,106 lines):**
`__init__.py`, `agent.py`, `config_display.py`, `context.py`, `credits.py`, `db.py`, `event_worker.py`, `gate.py`, `health.py`, `helpers.py`, `info.py`, `migrate.py`, `mission.py`, `playbook.py`, `project.py`, `report.py`, `scheduler.py`, `server.py`, `telegram.py`, `testing.py`, `worker.py`

### Move 2: Telegram (`modules/telegram/` → `modules/clients/telegram/`)

Entire package moves. Import path changes from `modules.telegram.*` to `modules.clients.telegram.*`.

### Move 3: TUI (`modules/tui/` → `modules/clients/tui/`)

Skeleton moves. Import path changes from `modules.tui.*` to `modules.clients.tui.*`.

### Extract 4: Shared Primitives → `modules/clients/common/`

**`common/display.py`** — extracted from `report.py` lines 27-271:
- `DOTTED_ROWS` — custom box style
- `OUTPUT_FORMATS` — format tuple
- `get_console()` — console factory
- `status_color()` / `styled_status()` — status formatting
- `build_table()` — declarative table builder
- `status_panel()` / `info_panel()` / `primary_panel()` — panel builders
- `thinking_panel()` / `output_panel()` — content panels
- `format_json_body()` — JSON syntax highlighting
- `cost_line()` / `summary_table()` — cost/stats display
- `severity_color()` — severity formatting

**`common/gate_helpers.py`** — extracted from `cli/gate.py`:
- `cost_color(cost, budget)` — budget ratio coloring
- `status_icon(status)` — status symbols (✓, ✗, ⏱, —)
- `gate_header(ctx, title)` — formatted gate header

**`common/service_bridge.py`** — deferred to Plan 23 Phase 1 (TUI):
- Will wrap `ProjectService.factory()`, `MissionService.factory()`, etc.
- Will be used by CLI commands, TUI, and potentially Telegram

---

## Import Path Changes

### Internal CLI imports (9 files import from report.py)

```python
# Before
from modules.backend.cli.report import get_console, build_table, styled_status

# After — CLI handlers still import from report.py (re-exports from common.display)
from modules.clients.cli.report import get_console, build_table, styled_status

# New code and TUI can import directly from common:
from modules.clients.common.display import get_console, build_table, styled_status
```

### Root cli.py (all command registrations)

```python
# Before
from modules.backend.cli.health import check_health
from modules.backend.cli.server import run_server

# After
from modules.clients.cli.health import check_health
from modules.clients.cli.server import run_server
```

### Backend gate.py (circular dependency fix)

```python
# Before (backend importing from client — wrong!)
from modules.backend.cli.gate import CliGateReviewer

# After (backend imports from clients — correct direction)
from modules.clients.cli.gate import CliGateReviewer
```

### Telegram internal imports

```python
# Before
from modules.telegram.handlers.common import router

# After
from modules.clients.telegram.handlers.common import router
```

### CLI files importing from backend (NO CHANGE)

```python
# These stay the same — clients importing from backend is correct
from modules.backend.services.project import ProjectService
from modules.backend.agents.mission_control.gate import GateContext
from modules.backend.core.config import get_app_config
```

---

## report.py Split

The 867-line `report.py` splits into two files:

**`modules/clients/common/display.py` (219 lines)**
- All Rich primitives (console, tables, panels, formatting) with keyword-only APIs
- Constants (OUTPUT_FORMATS, DOTTED_ROWS, SEVERITY_ORDER, color maps)
- Pure display helpers with no business logic

**`modules/clients/cli/report.py` (638 lines)**
- Re-exports all display primitives from `common.display` for backwards compatibility
- `render_human()` — dynamic JSON-to-table rendering
- `render_task_outputs()` / `render_mission_outcomes()` — task output rendering
- `colorize_narrative()` — Rich markup for narratives
- `render_mission()` / `render_playbook_run()` — async report renderers (call synthesis agent)
- `generate_narrative()` / `playbook_run_to_dict()` — public helpers used by playbook.py

Note: report.py exceeds the 500-line target because it also serves as the re-export surface for display primitives (keeping existing CLI handler imports stable). No good split point remains without breaking the re-export pattern.

---

## Execution Order (as completed)

1. Created `modules/clients/` package structure with `common/`, `cli/`, `tui/`, `telegram/`
2. Extracted `common/display.py` from `report.py` (~219 lines of pure display primitives)
3. Extracted `common/gate_helpers.py` from `gate.py` (~51 lines)
4. Moved CLI from `backend/cli/` to `clients/cli/`, updated all internal imports
5. Moved Telegram from `modules/telegram/` to `clients/telegram/`, updated internal imports
6. Moved TUI from `modules/tui/` to `clients/tui/`
7. Updated root `cli.py` entry point (29 import path changes)
8. Fixed `backend/agents/mission_control/gate.py` import → `modules.clients.cli.gate`
9. Updated `backend/main.py` and `backend/gateway/registry.py` telegram imports
10. Updated test mock patch strings in `tests/unit/telegram/`
11. Deleted old directories: `modules/backend/cli/`, `modules/telegram/`, `modules/tui/`
12. Updated `docs/05-rules/006_display_centralization.jsonl` to new paths
13. Updated Plan 23 paths from `modules/tui/` → `modules/clients/tui/`
14. Enforced keyword-only args on all 8 display primitives (rule 006.6)
15. Renamed `_SEVERITY_ORDER` → `SEVERITY_ORDER` (public API)
16. Made `generate_narrative` / `playbook_run_to_dict` public (were private but cross-module)
17. Refactored `gate.py` to use `build_table()` instead of raw `Table()` (rule 006.2)
18. Fixed `status_icon()` fallback to wrap unknown statuses in `[dim]` markup
19. Added 57 unit tests for `common/display.py` and `common/gate_helpers.py`
20. Verified: `python cli.py --help`, all imports, all rule checks, 116 tests pass

---

## Risk Assessment

**Low risk** — this is a mechanical refactor:
- No logic changes, only import paths
- All files keep their names and internal structure
- `git mv` preserves history
- Two external consumers: `cli.py` (root) and `backend/.../gate.py` (one import)
- Telegram has ~15 internal cross-imports to update

**Only breaking change**: `modules.backend.agents.mission_control.gate` imports `CliGateReviewer` from `modules.backend.cli.gate`. This is already a layer violation (backend → client). The fix moves it to `modules.clients.cli.gate` — still a cross-layer import but now explicit and in the correct direction.

---

## Verification

1. `python -c "from modules.clients.cli.report import render_mission"` — CLI report loads
2. `python -c "from modules.clients.common.display import get_console"` — common display loads
3. `python -c "from modules.clients.telegram.bot import create_bot"` — telegram loads
4. `python cli.py --help` — root CLI still works
5. `python -m pytest tests/ -x` — existing tests pass
6. `grep -r "from modules.backend.cli" --include="*.py"` — returns zero results
7. `grep -r "from modules.telegram" --include="*.py"` — returns zero results (all moved to `modules.clients.telegram`)
