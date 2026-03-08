# BFA Platform CLI Usage

All platform operations go through a single entry point: `python cli.py`.

```
python cli.py --help
```

---

## 1. Setup & Infrastructure

### Start the API server

```bash
python cli.py --service server --verbose
python cli.py --service server --port 8099 --reload
```

### Stop / restart the server

```bash
python cli.py --service server --action stop
python cli.py --service server --action restart
python cli.py --service server --action status
```

### Database migrations

```bash
# Check current migration state
python cli.py --service migrate

# Run all pending migrations
python cli.py --service migrate --migrate-action upgrade --revision head

# Generate a new migration from model changes
python cli.py --service migrate --migrate-action autogenerate -m "add new table"

# View migration history
python cli.py --service migrate --migrate-action history
```

### View configuration and app info

```bash
python cli.py --service config
python cli.py --service info
```

### Health check

```bash
python cli.py --service health --verbose
```

---

## 2. Agent Dispatch (Single Agent)

Send a message to an agent. Mission Control routes to the best agent automatically, or you can target one directly.

### Auto-routed

```bash
python cli.py --service agent --agent-message "run a health check" --verbose
python cli.py --service agent --agent-message "scan code quality in modules/backend" --verbose
```

### Direct agent targeting (bypass routing)

```bash
python cli.py --service agent --agent-message "check for import violations" --agent-name code.qa.agent
python cli.py --service agent --agent-message "audit system health" --agent-name system.health.agent
```

---

## 3. Mission Lifecycle (Multi-Agent Dispatch)

Missions are the core execution primitive. A mission takes an objective, generates a plan via the Planning Agent (Opus with extended thinking), validates the plan against 11 rules, dispatches tasks to agents in topological order with parallelism, runs 3-tier verification on each result, and persists everything.

### One-shot: create + execute

```bash
python cli.py --service mission --mission-action run \
  --objective "audit the platform: run a code quality scan and a system health check" \
  --verbose
```

### With budget ceiling

```bash
python cli.py --service mission --mission-action run \
  --objective "full platform audit" \
  --budget 2.00 \
  --verbose
```

### Two-step: create then execute

```bash
# Step 1: Create (PENDING state)
python cli.py --service mission --mission-action create \
  --objective "scan for security violations"

# Step 2: Execute (PENDING → RUNNING → COMPLETED)
python cli.py --service mission --mission-action execute \
  --mission-id <id from step 1> \
  --verbose
```

### Inspect missions

```bash
# List all missions
python cli.py --service mission --mission-action list

# Detailed view (task executions, verification outcomes)
python cli.py --service mission --mission-action detail --mission-id <id>

# Cost breakdown (per-task tokens and cost)
python cli.py --service mission --mission-action cost --mission-id <id>
```

Note: `list` queries the `missions` table (lifecycle tracking). `detail` and `cost` query `mission_records` (execution history). The IDs are different — use `list` to find the mission ID, and check the logs or `query` the `mission_records` table for the record ID.

---

## 4. Database Management

### Inspect

```bash
# Row counts for all tables
python cli.py --service db --db-action stats

# Table schemas (columns, types, nullability)
python cli.py --service db --db-action tables

# Query recent rows from a specific table
python cli.py --service db --db-action query --table missions
python cli.py --service db --db-action query --table task_executions --limit 5
python cli.py --service db --db-action query --table session_messages --limit 20
```

Available tables: `missions`, `playbook_runs`, `mission_records`, `task_executions`, `task_attempts`, `mission_decisions`, `sessions`, `session_channels`, `session_messages`, `notes`.

### Clear data (for testing)

```bash
# Clear EVERYTHING (all tables)
python cli.py --service db --db-action clear --yes

# Clear mission data only (missions, records, executions, decisions)
python cli.py --service db --db-action clear-missions --yes

# Clear session data only (sessions, channels, messages)
python cli.py --service db --db-action clear-sessions --yes
```

Without `--yes`, you will be prompted for confirmation.

---

## 5. Testing

```bash
# Run all unit tests
python cli.py --service test --test-type unit

# Run with coverage
python cli.py --service test --test-type unit --coverage

# Run integration or e2e tests
python cli.py --service test --test-type integration
python cli.py --service test --test-type e2e
```

---

## 6. Background Services

```bash
# Task worker (Celery/SAQ)
python cli.py --service worker --workers 2

# Scheduler (periodic tasks)
python cli.py --service scheduler

# Telegram polling bot
python cli.py --service telegram-poll

# Event worker
python cli.py --service event-worker
```

All long-running services support `--action stop/restart/status`.

---

## Full Workflow Example

A complete cycle from clean slate to inspected results:

```bash
# 1. Ensure migrations are current
python cli.py --service migrate --migrate-action upgrade --revision head

# 2. Clear any previous test data
python cli.py --service db --db-action clear --yes

# 3. Verify clean state
python cli.py --service db --db-action stats

# 4. Run a mission
python cli.py --service mission --mission-action run \
  --objective "audit the platform: run a code quality scan and a system health check" \
  --budget 2.00 \
  --verbose

# 5. List missions
python cli.py --service mission --mission-action list

# 6. Check what was persisted
python cli.py --service db --db-action stats
python cli.py --service db --db-action query --table missions
python cli.py --service db --db-action query --table task_executions

# 7. Get cost breakdown (use the mission_records ID from query output)
python cli.py --service mission --mission-action cost --mission-id <record-id>

# 8. Run tests to confirm nothing broke
python cli.py --service test --test-type unit
```

---

## Production Rename

> **Note:** "BFA Platform" is the reference architecture name. When deploying to production, rename the platform, database, and user to your chosen identity (e.g., "Tachikoma", your product name, etc.). Search for `bfa` in config files, CLI, and tests.

---

## Global Options

| Flag | Short | Description |
|------|-------|-------------|
| `--service` | `-s` | Service to run (default: `info`) |
| `--action` | `-a` | Lifecycle action: `start`, `stop`, `restart`, `status` |
| `--verbose` | `-v` | INFO-level logging |
| `--debug` | `-d` | DEBUG-level logging |
| `--yes` | `-y` | Skip confirmation prompts |
