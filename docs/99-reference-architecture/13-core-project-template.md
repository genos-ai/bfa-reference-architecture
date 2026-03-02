# 13 - Project Template

*Version: 1.1.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.1.0 (2025-01-29): Added data/ directory for file-based data storage
- 1.0.0 (2025-01-27): Initial project template structure

---

## Purpose

This document defines the standard directory structure for new projects. All projects should follow this layout to ensure consistency and enable developers to navigate any project immediately.

---

## Context

The fastest way to slow down a development team is to let every project invent its own directory structure. Developers waste time figuring out where things go, AI assistants make inconsistent assumptions about file locations, and cross-project contributions require relearning the layout each time. This template ensures every project is navigable on first contact.

The layout directly implements the patterns from multiple other standards: the layered backend architecture (03) maps to `api/`, `services/`, `repositories/`, `models/`; module structure (04) maps to the `modules/` directory; testing standards (11) map to the hybrid `tests/unit/`, `tests/integration/`, `tests/e2e/` layout; and configuration standards (03) map to `config/` with `.env` and YAML files.

The key decision is that this structure applies from day one, even for small projects. The overhead of a few empty directories is negligible compared to the cost of restructuring a growing project later. The `.project_root` marker file enables reliable root detection from anywhere in the directory tree, which is used by configuration loading, logging setup, and test discovery.

---

## Complete Project Structure

```
{project}/
├── .gitignore
├── .project_root                   # Root marker
├── README.md
├── requirements.txt
├── pytest.ini
│
├── data/                           # Runtime artifacts (not tracked)
│   ├── README.md
│   ├── logs/                       # Application logs
│   │   └── .gitkeep
│   └── cache/                      # Temporary/cached files
│       └── .gitkeep
│
├── config/
│   ├── .env.example                # Required env vars
│   └── settings/
│       ├── application.yaml        # App config
│       ├── database.yaml           # DB config
│       ├── logging.yaml            # Log config
│       └── features.yaml           # Feature flags
│
├── docs/
│   ├── README.md                   # Docs index
│   ├── 01-getting-started/
│   │   └── README.md               # Setup, installation, quickstart
│   ├── 02-architecture/
│   │   └── README.md               # System design, diagrams
│   ├── 03-implementation/
│   │   └── README.md               # Plans, checklists, progress tracking
│   └── 04-reference/
│       ├── README.md
│       └── architecture-standards/ # Architecture standards (31 files)
│           ├── 00-overview.md
│           ├── # --- Core Foundation (01-09) ---
│           ├── 01-core-principles.md
│           ├── 02-primitive-identification.md
│           ├── 03-backend-architecture.md
│           ├── 04-module-structure.md
│           ├── 05-authentication.md
│           ├── 06-security-standards.md
│           ├── 07-data-protection.md
│           ├── 08-python-coding-standards.md
│           ├── 09-error-codes.md
│           ├── # --- Core Operations (10-16) ---
│           ├── 10-observability.md
│           ├── 11-testing-standards.md
│           ├── 12-development-workflow.md
│           ├── 13-project-template.md
│           ├── 14-background-tasks.md
│           ├── 15-deployment-bare-metal.md
│           ├── 16-deployment-azure.md
│           ├── # --- Optional Platform (20-26) ---
│           ├── 20-data-layer.md
│           ├── 21-event-architecture.md
│           ├── 22-frontend-architecture.md
│           ├── 23-typescript-coding-standards.md
│           ├── 24-llm-integration.md
│           ├── 25-telegram-bot-integration.md
│           ├── 26-telegram-client-integration.md
│           ├── 27-tui-architecture.md
│           ├── 28-cli-architecture.md
│           ├── # --- AI-First Platform (40-46) ---
│           ├── 40-agentic-architecture.md
│           ├── 41-agentic-pydanticai.md
│           ├── 42-agent-first-infrastructure.md
│           ├── 43-ai-first-interface-design.md
│           ├── 44-multi-channel-gateway.md
│           └── 46-event-session-architecture.md
│
├── modules/
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── migrations/             # Database migrations
│   │   │   ├── alembic.ini
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── health.py           # Health check endpoints
│   │   │   └── v1/
│   │   │       ├── __init__.py     # v1 router
│   │   │       └── endpoints/
│   │   │           └── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py           # Settings loader
│   │   │   ├── config_schema.py    # Pydantic schemas for YAML config
│   │   │   ├── database.py         # DB connection
│   │   │   ├── dependencies.py     # FastAPI dependencies
│   │   │   ├── exceptions.py       # Custom exceptions
│   │   │   ├── logging.py          # Logging setup
│   │   │   ├── middleware.py        # Request context middleware
│   │   │   ├── security.py         # Auth utilities
│   │   │   └── utils.py            # Utilities (utc_now)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── base.py             # SQLAlchemy base
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   └── base.py             # Base repository
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── base.py             # Base schemas
│   │   ├── services/
│   │   │   └── __init__.py
│   │   ├── agents/                  # PydanticAI agents
│   │   │   ├── coordinator/         # Agent routing, model construction
│   │   │   ├── vertical/            # Domain-specific agents
│   │   │   ├── deps/                # Shared dependency types
│   │   │   └── tools/               # Shared tool implementations
│   │   ├── gateway/                 # Channel adapter registry
│   │   │   ├── adapters/
│   │   │   └── security/            # Rate limiting, startup checks
│   │   ├── tasks/                   # Background tasks (Taskiq)
│   │   │   └── __init__.py
│   │   └── cli/                     # CLI subcommand modules
│   │       └── __init__.py
│   │
│   ├── telegram/                    # Telegram bot (client module)
│   │   ├── handlers/
│   │   ├── callbacks/
│   │   ├── keyboards/
│   │   ├── middlewares/
│   │   ├── services/
│   │   └── states/
│   │
│   └── frontend/
│       ├── index.html
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       ├── tailwind.config.js
│       ├── postcss.config.js
│       ├── public/
│       │   └── favicon.ico
│       └── src/
│           ├── main.tsx            # Entry point
│           ├── App.tsx
│           ├── index.css           # Tailwind imports
│           ├── components/
│           │   ├── ui/             # shadcn/ui components
│           │   └── features/       # Feature components
│           ├── hooks/              # Custom hooks
│           ├── lib/
│           │   ├── api.ts          # API client
│           │   └── utils.ts        # Utilities
│           ├── pages/              # Route components
│           ├── stores/             # Zustand stores
│           └── types/              # TypeScript types
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Root fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── conftest.py             # Unit test fixtures (mocks)
│   │   └── backend/
│   │       ├── services/
│   │       ├── repositories/
│   │       └── core/
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── conftest.py             # Integration fixtures (real DB)
│   │   └── backend/
│   │       ├── api/
│   │       └── workflows/
│   └── e2e/
│       ├── __init__.py
│       └── conftest.py             # E2E fixtures
│
└── scripts/
    └── README.md
```

---

## Root Files

| File | Purpose |
|------|---------|
| `.gitignore` | Git ignore patterns |
| `.project_root` | Marker file for project root detection |
| `README.md` | Project overview, setup instructions |
| `requirements.txt` | Python dependencies |
| `pytest.ini` | Pytest configuration |

---

## Data Directory

The `data/` directory contains runtime artifacts. Not tracked in git.

| Path | Purpose |
|------|---------|
| `logs/` | Application logs |
| `data/cache/` | Temporary/cached files |

---

## Config Directory

Configuration files separated from code.

| Path | Purpose |
|------|---------|
| `config/.env.example` | Template for required environment variables |
| `config/settings/application.yaml` | Application settings |
| `config/settings/database.yaml` | Database configuration |
| `config/settings/logging.yaml` | Logging configuration |
| `config/settings/features.yaml` | Feature flags |

### Environment Variables

The `.env.example` file documents all required environment variables:

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=appname
DB_USER=
DB_PASSWORD=

# Redis
REDIS_URL=redis://localhost:6379

# Security
JWT_SECRET=
API_KEY_SALT=

# External Services
# Add as needed
```

---

## Docs Directory

Documentation organized by purpose.

| Path | Purpose |
|------|---------|
| `docs/README.md` | Documentation index |
| `docs/01-getting-started/` | Installation, setup, quickstart |
| `docs/02-architecture/` | System design, diagrams, decisions |
| `docs/03-implementation/` | Plans, checklists, progress tracking |
| `docs/04-reference/` | Standards, API docs, external references |
| `docs/04-reference/architecture-standards/` | Architecture standards documents |

---

## Backend Module

The backend follows a layered architecture.

### Directory Purposes

| Directory | Purpose |
|-----------|---------|
| `api/` | HTTP endpoint handlers |
| `api/health.py` | Health check endpoints (not versioned) |
| `api/v1/` | Version 1 API endpoints |
| `api/v1/endpoints/` | Individual endpoint modules by domain |
| `core/` | Shared utilities, configuration, middleware |
| `models/` | SQLAlchemy database models |
| `repositories/` | Data access layer |
| `schemas/` | Pydantic request/response schemas |
| `services/` | Business logic |
| `tasks/` | Background task definitions |
| `migrations/` | Database migrations (Alembic) |

### API Layer Structure

```
api/
├── __init__.py
├── health.py              # /health, /health/ready, /health/detailed
└── v1/
    ├── __init__.py        # Combines all v1 routers
    └── endpoints/
        ├── __init__.py
        ├── users.py       # /api/v1/users/*
        └── projects.py    # /api/v1/projects/*
```

### Wiring Example

```python
# main.py
from fastapi import FastAPI
from modules.backend.api import health
from modules.backend.api.v1 import router as api_v1_router

app = FastAPI(title="App Name")

# Health endpoints (no prefix)
app.include_router(health.router)

# API v1 endpoints
app.include_router(api_v1_router, prefix="/api/v1")
```

```python
# api/v1/__init__.py
from fastapi import APIRouter
from modules.backend.api.v1.endpoints import users, projects

router = APIRouter()
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(projects.router, prefix="/projects", tags=["projects"])
```

---

## Frontend Module

React frontend with Vite.

### Directory Purposes

| Directory | Purpose |
|-----------|---------|
| `src/components/ui/` | Reusable UI primitives (shadcn/ui) |
| `src/components/features/` | Feature-specific components |
| `src/hooks/` | Custom React hooks |
| `src/lib/` | Utilities, API client |
| `src/pages/` | Route components |
| `src/stores/` | Zustand state stores |
| `src/types/` | TypeScript type definitions |

### Technology Stack

| Concern | Solution |
|---------|----------|
| Framework | React (latest stable) |
| Build | Vite |
| Language | TypeScript (strict mode) |
| Styling | Tailwind CSS |
| Components | shadcn/ui |
| Server State | TanStack Query |
| Client State | Zustand |
| Forms | react-hook-form + zod |

---

## Tests Directory

Tests use a hybrid structure: test type at top level, source structure within.

See **11-testing-standards.md** for complete testing guidance.

| Path | Purpose |
|------|---------|
| `tests/conftest.py` | Root fixtures (event loop, shared utilities) |
| `tests/unit/` | Unit tests (fast, mocked dependencies) |
| `tests/unit/conftest.py` | Unit test fixtures (mocks) |
| `tests/integration/` | Integration tests (real database) |
| `tests/integration/conftest.py` | Integration fixtures (real DB session) |
| `tests/e2e/` | End-to-end tests (full stack) |
| `tests/e2e/conftest.py` | E2E fixtures (browser, full stack) |

### Test Structure Convention

See **11-testing-standards.md** for the complete test directory structure, fixture hierarchy, and naming conventions. The template provides the base directories; doc 11 defines the rules.

---

## Creating a New Project

1. Copy this template structure
2. Replace `{project}` with your project name
3. Update `README.md` with project-specific information
4. Copy `.env.example` to `.env` and fill in values
5. Initialize git repository
6. Install dependencies:
   ```bash
   # Backend (using uv - recommended for web apps)
   uv venv
   source .venv/bin/activate
   uv pip install -r requirements.txt
   
   # Alternative: conda (for data/ML projects)
   # conda create -n project python=3.12 && conda activate project
   # pip install -r requirements.txt
   
   # Frontend
   cd modules/frontend
   npm install
   ```
7. Run database migrations:
   ```bash
   python cli.py --service migrate --migrate-action upgrade
   ```
8. Start development servers:
   ```bash
   # Backend
   uvicorn modules.backend.main:app --reload
   
   # Frontend
   cd modules/frontend && npm run dev
   ```

---

## Checklist for New Projects

- [ ] `.project_root` file created
- [ ] `.gitignore` configured (including data/ rules)
- [ ] `README.md` customized
- [ ] `.env.example` lists all required variables
- [ ] `config/settings/*.yaml` files configured
- [ ] `docs/01-getting-started/README.md` has setup instructions
- [ ] Architecture standards copied to `docs/04-reference/`
- [ ] Database models defined in `models/`
- [ ] Initial Alembic migration created
- [ ] Health endpoints working
- [ ] Frontend builds successfully
- [ ] Tests directory structure in place
- [ ] Data directory structure in place (if handling file-based data)
