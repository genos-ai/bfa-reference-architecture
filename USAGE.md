# BFA Platform CLI Usage

All platform operations go through a single entry point: `python cli.py`.

```
python cli.py --help
python cli.py <command> --help
```

---

## 1. Setup & Infrastructure

### Start the API server

```bash
python cli.py --verbose server start
python cli.py server start --port 8099 --reload
```

### Stop / restart the server

```bash
python cli.py server stop
python cli.py server restart
python cli.py server status
```

### Database migrations

```bash
# Check current migration state
python cli.py migrate

# Run all pending migrations
python cli.py migrate upgrade head

# Generate a new migration from model changes
python cli.py migrate autogenerate -m "add new table"

# View migration history
python cli.py migrate history
```

### View configuration and app info

```bash
python cli.py config
python cli.py info
```

### Health check

```bash
python cli.py health --verbose
```

---

## 2. Agent Dispatch (Single Agent)

Send a message to an agent. Mission Control routes to the best agent automatically, or you can target one directly.

### Auto-routed

```bash
python cli.py agent "run a health check" --verbose
python cli.py agent "scan code quality in modules/backend" --verbose
```

### Direct agent targeting (bypass routing)

```bash
python cli.py agent "check for import violations" --name code.qa.agent
python cli.py agent "audit system health" --name system.health.agent
```

---

## 3. Mission Lifecycle (Multi-Agent Dispatch)

Missions are the core execution primitive. A mission takes an objective, generates a plan via the Planning Agent (Opus with extended thinking), validates the plan against 11 rules, dispatches tasks to agents in topological order with parallelism, runs 3-tier verification on each result, and persists everything.

### One-shot: create + execute

```bash
python cli.py --verbose mission run \
  "audit the platform: run a code quality scan and a system health check"
```

### With budget ceiling

```bash
python cli.py --verbose mission run "full platform audit" --budget 2.00
```

### Two-step: create then execute

```bash
# Step 1: Create (PENDING state)
python cli.py mission create "scan for security violations"

# Step 2: Execute (PENDING → RUNNING → COMPLETED)
python cli.py --verbose mission execute <id from step 1>
```

### Inspect missions

```bash
# List all missions
python cli.py mission list

# Detailed view (task executions, verification outcomes)
python cli.py mission detail <id>

# Cost breakdown (per-task tokens and cost)
python cli.py mission cost <id>
```

Note: `list` queries the `missions` table (lifecycle tracking). `detail` and `cost` query `mission_records` (execution history). The IDs are different — use `list` to find the mission ID, and check the logs or `query` the `mission_records` table for the record ID.

---

## 4. Database Management

### Inspect

```bash
# Row counts for all tables
python cli.py db stats

# Table schemas (columns, types, nullability)
python cli.py db tables

# Query recent rows from a specific table
python cli.py db query missions
python cli.py db query task_executions --limit 5
python cli.py db query session_messages --limit 20
```

Available tables: `missions`, `playbook_runs`, `mission_records`, `task_executions`, `task_attempts`, `mission_decisions`, `sessions`, `session_channels`, `session_messages`, `notes`.

### Clear data (for testing)

```bash
# Clear EVERYTHING (all tables)
python cli.py db clear --yes

# Clear mission data only (missions, records, executions, decisions)
python cli.py db clear-missions --yes

# Clear session data only (sessions, channels, messages)
python cli.py db clear-sessions --yes
```

Without `--yes`, you will be prompted for confirmation.

---

## 5. Playbook Execution (Repeatable Multi-Agent Workflows)

Playbooks are YAML-defined multi-step workflows that execute missions in dependency order. Unlike dynamic missions where the Planning Agent decides everything at runtime, playbooks provide repeatable, deterministic execution plans.

### List available playbooks

```bash
python cli.py playbook list
```

### Inspect a playbook

```bash
python cli.py playbook detail ops.platform-audit
```

### Execute a playbook

```bash
# Default output (AI-generated summary)
python cli.py --verbose playbook run ops.platform-audit

# With specific output format
python cli.py playbook run ops.platform-audit --output detail
python cli.py playbook run ops.platform-audit --output json
```

### List playbook runs

```bash
python cli.py playbook runs
```

### Inspect a specific run (with missions)

```bash
python cli.py playbook run-detail <id>
```

### Render a report for a past run

```bash
# AI-generated narrative summary (default)
python cli.py playbook report <id>

# Deterministic per-step breakdown
python cli.py playbook report <id> --output detail

# Raw structured JSON
python cli.py playbook report <id> --output json
```

---

## 6. Preflight Credit Check

Before running missions or playbooks, verify that all models in the roster have available credits. This is done automatically when you run a mission or playbook, but you can also run it standalone.

### Check default roster

```bash
python cli.py credits
```

### Check a specific roster

```bash
python cli.py credits --roster default
```

Output shows pass/fail per model:

```
Preflight credit check (roster: default)...

✓ PASS  anthropic:claude-haiku-4-5-20251001 (287ms)
✓ PASS  anthropic:claude-opus-4-20250514 (312ms)

All models OK — ready to run missions and playbooks.
```

The check is **provider-agnostic** — it uses the same model-building path as agents (PydanticAI), so it works with any provider configured in the roster. Each unique model gets a one-token ping (~$0.004 total).

Mission and playbook `run`/`execute` actions automatically run preflight and abort if any model lacks credits, so you never burn orchestration time on a doomed run.

---

## 7. Codebase Intelligence

### Code Map — structural skeleton ranked by PageRank

```bash
# Markdown tree to stdout (default, most token-efficient for LLMs)
python scripts/generate_code_map.py --scope modules/

# With token budget (fits context windows)
python scripts/generate_code_map.py --scope modules/ --max-tokens 4096

# JSON output (for programmatic access, Planning Agent, QA agent)
python scripts/generate_code_map.py --scope modules/ --format json --pretty

# Summary statistics only
python scripts/generate_code_map.py --scope modules/ --stats

# Save to .codemap/ (gitignored)
python scripts/generate_code_map.py --scope modules/ --format json --pretty -o .codemap/map.json
python scripts/generate_code_map.py --scope modules/ -o .codemap/map.md

# Generate CODEMAP.md at project root (agent-friendly, config schemas excluded)
python scripts/generate_code_map.py --scope modules/ --exclude "**/config_schema.py" --max-tokens 4096 -o CODEMAP.md
```

The `--exclude` flag supports directory prefixes (`tests/`), exact paths (`modules/backend/core/config.py`), and glob patterns (`**/config_schema.py`, `*.generated.py`).

### PyQuality Index (PQI) — composite 0-100 code quality score

```bash
# Score modules/ with all 7 dimensions
python scripts/score_quality.py

# Include code map for accurate modularity scoring (recommended)
python scripts/score_quality.py --with-code-map

# Include tests in scope for accurate testability scoring
python scripts/score_quality.py --scope modules/ tests/ --with-code-map

# Show per-dimension sub-scores and actionable recommendations
python scripts/score_quality.py --with-code-map --recommendations

# JSON output (for agents, dashboards, trend tracking)
python scripts/score_quality.py --with-code-map --json

# Run with Bandit security linter (requires: pip install bandit)
python scripts/score_quality.py --use-bandit --recommendations

# Run with Radon complexity analyzer (requires: pip install radon)
python scripts/score_quality.py --use-radon --recommendations

# Run with all external tools
python scripts/score_quality.py --use-bandit --use-radon --with-code-map --recommendations

# Alternative weight profiles
python scripts/score_quality.py --profile library
python scripts/score_quality.py --profile safety_critical
```

---

## 8. Testing

```bash
# Run all unit tests
python cli.py test unit

# Run with coverage
python cli.py test unit --coverage

# Run integration or e2e tests
python cli.py test integration
python cli.py test e2e
```

---

## 9. Background Services

```bash
# Task worker
python cli.py worker --workers 2

# Scheduler (periodic tasks)
python cli.py scheduler

# Telegram polling bot
python cli.py telegram

# Event worker
python cli.py event-worker
```

Server lifecycle is managed via subcommands: `python cli.py server stop/status/restart`.

---

## Full Workflow Example

A complete cycle from clean slate to inspected results:

```bash
# 1. Ensure migrations are current
python cli.py migrate upgrade head

# 2. Clear any previous test data
python cli.py db clear --yes

# 3. Verify clean state
python cli.py db stats

# 4. Check credits before running anything
python cli.py credits

# 5. Run a mission
python cli.py --verbose mission run \
  "audit the platform: run a code quality scan and a system health check" \
  --budget 2.00

# 6. List missions
python cli.py mission list

# 7. Check what was persisted
python cli.py db stats
python cli.py db query missions
python cli.py db query task_executions

# 8. Get cost breakdown (use the mission_records ID from query output)
python cli.py mission cost <record-id>

# 9. Run tests to confirm nothing broke
python cli.py test unit
```

---

## Production Rename

> **Note:** "BFA Platform" is the reference architecture name. When deploying to production, rename the platform, database, and user to your chosen identity (e.g., "Tachikoma", your product name, etc.). Search for `bfa` in config files, CLI, and tests.

---

## Global Options

| Flag | Short | Description |
|------|-------|-------------|
| `--verbose` | `-v` | INFO-level logging |
| `--debug` | `-d` | DEBUG-level logging |

Per-command options (like `--output`, `--budget`, `--yes`) are shown in each command's `--help`.
