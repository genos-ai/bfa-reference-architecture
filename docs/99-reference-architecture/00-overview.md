# Architecture Standards Overview

*Version: 3.4.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 3.4.0 (2026-03-10): Added 49-agentic-codebase-intelligence.md for coding agent structural awareness — Code Map (tree-sitter + PageRank), Exemplar Registry, Task File Manifest, decomposed generator pipeline, Context Assembly Layer 3, coding agent contract
- 3.3.0 (2026-03-10): Added 48-agentic-project-context.md for persistent cross-mission project context — Project entity, Project Context Document (PCD), three-layer memory model, agent contract, context assembly, fractal summarization
- 3.2.0 (2026-03-03): Added Technology Stack Quick Reference — definitive technology choices across all docs for quick agent/developer lookup
- 3.1.0 (2026-02-26): Added 47-agent-module-organization.md for agent system layout, naming conventions, agent types, shared tool architecture, layered prompt system, access control model
- 3.0.0 (2026-02-26): Renumbered all docs into clean groups — Core Foundation (01-09), Core Operations (10-16), Optional Platform (20-28), AI-First Platform (40-46); added Architecture Profiles; removed cross-contamination (core docs no longer reference AI docs); dependency flows one way (AI→core, never core→AI)
- 2.4.0 (2026-02-26): Added 46-event-session-architecture.md (was 31) for event-driven sessions, streaming coordinator, plan management, memory architecture, approval gates
- 2.3.0 (2026-02-24): Added 44-multi-channel-gateway.md (was 29) for channel adapters, session management, real-time push, gateway security; updated 01 with P8 Secure by Default
- 2.2.0 (2026-02-24): Added 27-tui-architecture.md (was 28) for interactive terminal interface (Textual)
- 2.1.0 (2026-02-20): Added 42-agent-first-infrastructure.md (was 27) for MCP, A2A, agent identity, intent APIs, agent-discoverable endpoints
- 2.0.0 (2026-02-19): Consolidated agentic docs — trimmed conceptual to framework-agnostic, rewrote implementation with PydanticAI-native patterns
- 1.9.0 (2026-02-18): Split agentic docs into conceptual and PydanticAI implementation
- 1.8.0 (2026-02-18): Added agentic AI architecture for agents, orchestration, tools, memory
- 1.7.0 (2026-02-18): Added Telegram Client API (MTProto) integration
- 1.6.0 (2026-02-18): Renumbered docs; moved deployment; added Azure deployment
- 1.5.0 (2026-02-13): Added Telegram bot integration (aiogram v3)
- 1.4.0 (2025-01-29): Added data/ directory structure for file-based data storage
- 1.3.0 (2025-01-29): Added Python environment management guide (uv vs conda)
- 1.2.0 (2025-01-29): Added testing standards
- 1.1.0 (2025-01-27): Added project template
- 1.0.0 (2025-01-27): Initial generic architecture standards

---

## Purpose

This document set defines architecture standards for software projects. It is prescriptive, not advisory. These are decisions, not options.

When a technology choice no longer serves the standard, the standard is updated. Individual projects do not deviate; the standard evolves.

---

## Architecture Profiles

This architecture serves two use cases. Choose your profile to know which docs apply.

### Profile: Traditional Backend

A Python/FastAPI backend with thin clients (web, CLI, Telegram). Stateless CRUD, standard request/response patterns.

**Adopt:** Core Foundation (01-09) + Core Operations (10-16) + Optional Platform (20-28) as needed.

**Ignore:** AI-First Platform (40-48) entirely.

### Profile: AI-First Platform (BFA)

An agent-first backend where AI agents are the primary consumers. Sessions, streaming, plans, memory, approval gates, multi-channel delivery.

**Adopt:** Core Foundation (01-09) + Core Operations (10-16) + Optional Platform (20-28) as needed + AI-First Platform (40-48).

**The core docs are the foundation for both profiles.** AI-First docs build on top of core — they never replace it. The service layer, repository layer, and API design patterns from core apply in both profiles.

---

## Document Groups

### Core Foundation (01-09)

These apply to all projects without exception. Architectural bedrock.

| Document | Purpose |
|----------|---------|
| 01-core-principles.md | Non-negotiable architectural mandates |
| 02-primitive-identification.md | Identifying the system's fundamental data type |
| 03-backend-architecture.md | Backend framework, service layer, API design |
| 04-module-structure.md | Module organization and inter-module communication |
| 05-authentication.md | Authentication and authorization |
| 06-security-standards.md | Application security (OWASP, cryptography, input handling) |
| 07-data-protection.md | Data protection and privacy (PII, GDPR, retention) |
| 08-python-coding-standards.md | Python file organization, imports, CLI, error handling |
| 09-error-codes.md | Error code registry, client handling guide |

### Core Operations (10-16)

Quality, workflow, and deployment. Apply to all projects.

| Document | Purpose |
|----------|---------|
| 10-observability.md | Logging, monitoring, debugging, alerting |
| 11-testing-standards.md | Test organization, fixtures, coverage |
| 12-development-workflow.md | Git workflow, CI/CD, testing, versioning |
| 13-project-template.md | Standard project directory structure |
| 14-background-tasks.md | Background tasks and scheduling (Taskiq) |
| 15-deployment-bare-metal.md | Self-hosted deployment (Ubuntu, systemd, nginx) |
| 16-deployment-azure.md | Azure managed services deployment |

### Optional Platform (20-28)

General-purpose capabilities. Adopt based on project needs. No AI concepts.

| Document | Adopt When |
|----------|------------|
| 20-data-layer.md | Need time-series, analytics, or advanced caching |
| 21-event-architecture.md | Need async processing, WebSocket, or message queues |
| 22-frontend-architecture.md | Building a web UI |
| 23-typescript-coding-standards.md | Building React frontend |
| 24-llm-integration.md | Integrating LLM capabilities (provider interface, cost tracking) |
| 25-telegram-bot-integration.md | Building Telegram bot interface |
| 26-telegram-client-integration.md | Need channel scraping, message history, or autonomous Telegram access |
| 27-tui-architecture.md | Interactive terminal interface (Textual + Textual Web) for persistent sessions, real-time streaming, dashboards |
| 28-cli-architecture.md | CLI architecture — Click groups + subcommands, AI-first discoverability, Rich output, service lifecycle, testing |

### AI-First Platform (40-49)

Agent architecture, session model, multi-channel delivery, persistent project context, codebase intelligence. Adopt for BFA projects.

| Document | Adopt When |
|----------|------------|
| 40-agentic-architecture.md | Agentic AI conceptual architecture — framework-agnostic (phases, principles, orchestration patterns, AgentTask primitive) |
| 41-agentic-pydanticai.md | Agentic AI implementation using PydanticAI (coordinator, agents, middleware, testing, database schema). Read 40 first. |
| 42-agent-first-infrastructure.md | Exposing platform to external agents (MCP, A2A), agent identity, intent APIs. Independent of 40/41. |
| 43-ai-first-interface-design.md | Making services consumable by AI agents alongside human clients (adapter registry, self-describing APIs, service factory) |
| 44-multi-channel-gateway.md | Delivering agent interactions through multiple messaging channels (Telegram, Slack, Discord, WebSocket) with cross-channel sessions |
| 46-event-session-architecture.md | Interactive conversations, streaming agent responses, multi-step plans with approval gates, long-running autonomous tasks, multi-channel sessions |
| 47-agent-module-organization.md | Agent system layout, naming conventions, agent types (vertical/horizontal), shared tool architecture, layered prompt system, access control model |
| 48-agentic-project-context.md | Persistent cross-mission project context — Project entity, PCD (living knowledge brief), three-layer memory, agent contract (context_updates), fractal summarization, context assembly with token budgeting. Required for multi-mission workflows. |
| 49-agentic-codebase-intelligence.md | Structural codebase awareness for coding agents — Code Map (tree-sitter + PageRank, dual JSON/Markdown format), Exemplar Registry (canonical pattern files in PCD), Task File Manifest (pre-computed file lists), decomposed generator pipeline, Context Assembly Layer 3. Recommended when project includes coding agents. |

---

## Scope

### In Scope

- Python backend services with thin clients
- Web frontends (React)
- Terminal user interfaces (Textual)
- Command-line interfaces
- Data pipelines and analytics
- General web applications
- AI-first agent platforms (BFA profile)

### Out of Scope

- Mobile-native applications
- Desktop applications (Electron/Tauri)
- Embedded systems
- Gaming applications

---

## Core Philosophy

The architecture is built on the principles defined in **01-core-principles.md**. The two most important:

- **P1: Backend Owns All Business Logic** — every rule, validation, calculation, and decision lives in the backend. Clients are presentation layers that present data, capture input, and handle UI concerns. See doc 01 for the full definition and business logic boundary.
- **P3: Single Source of Truth Per Entity** — one authoritative write source per data type. Caches, replicas, and analytical copies derive from the source.

Clients never:
- Validate business rules
- Transform data for storage
- Make decisions about application state
- Store business data locally (caching excepted)

### Simplicity Over Cleverness

Prefer boring, proven solutions over novel approaches. Code should be readable by developers unfamiliar with the codebase. Abstractions are introduced only when duplication becomes problematic.

### AI-Assisted Development

Architecture choices favor technologies with extensive AI training data. This maximizes effectiveness of AI coding assistants and reduces development friction.

---

## Technology Stack Quick Reference

Definitive technology choices across all docs. When building or modifying code, use these — no alternatives, no substitutions.

### Backend

| Concern | Technology | Doc |
|---------|-----------|-----|
| Language | **Python 3.12+** | 03 |
| Web framework | **FastAPI** (async-native, Pydantic integration, OpenAPI) | 03 |
| ASGI server (dev) | **uvicorn** with `--reload` | 03 |
| ASGI server (prod) | **gunicorn** + `UvicornWorker` | 15, 16 |
| Validation / schemas | **Pydantic v2** (request/response schemas, config validation) | 03 |
| Configuration (secrets) | **Pydantic Settings** (`config/.env` → `get_settings()`) | 03 |
| Configuration (app) | **YAML files** (`config/settings/*.yaml` → `get_app_config()`) | 03 |
| CLI | **Click** (groups + subcommands, `tree` for AI discoverability, Rich output) | 28 |
| Logging | **structlog** (JSON output, structured context binding) | 10 |
| Code formatting | **black** | 08 |
| Import sorting | **isort** | 08 |
| Linting | **flake8** | 08 |
| Type checking | **mypy** (strict mode) | 08 |
| Rate limiting | **slowapi** (sliding window, Redis-backed) | 06 |
| Password hashing | **bcrypt** (work factor 12+) or **Argon2id** | 06 |
| Pre-commit | **pre-commit** framework | 12 |

### Database & Storage

| Concern | Technology | Doc |
|---------|-----------|-----|
| Primary database | **PostgreSQL 16+** (single source of truth) | 03, 20 |
| ORM | **SQLAlchemy 2.0** (async, mapped_column style) | 20 |
| Migrations | **Alembic** (upgrade + downgrade scripts) | 20 |
| Cache / pub-sub / queues | **Redis** (caching, rate limiting, Taskiq broker, session events) | 14, 20, 21 |
| Time-series (optional) | **TimescaleDB** (PostgreSQL extension, hypertables) | 20 |
| Analytics (optional) | **DuckDB** (embedded, queries Parquet directly) | 20 |
| Analytical file format | **Parquet** (columnar, compressed) | 20 |

### Events & Messaging

| Concern | Technology | Doc |
|---------|-----------|-----|
| Event bus framework | **FastStream** (unified API over Redis/Kafka/NATS) | 21, Plan 10 |
| Domain events (durable) | **Redis Streams** via FastStream (consumer groups, DLQ) | 21 |
| Session events (ephemeral) | **Redis Pub/Sub** via FastStream (sub-millisecond, real-time) | 21, 46 |
| Background tasks | **Taskiq** with Redis broker (async-native, cron scheduling) | 14 |
| Long-running workflows (Tier 4) | **Temporal** (durable execution, crash recovery, multi-day tasks) | 46 |

### Frontend (Web)

| Concern | Technology | Doc |
|---------|-----------|-----|
| Framework | **React** (latest stable) | 22 |
| Build tool | **Vite** (HMR, fast builds) | 22 |
| Language | **TypeScript** (strict mode) | 23 |
| Styling | **Tailwind CSS** (only approved styling approach) | 22 |
| UI components | **shadcn/ui** | 22 |
| Server state | **TanStack Query** (caching, refetching, stale-while-revalidate) | 22 |
| Client state | **Zustand** (minimal, granular subscriptions) | 22 |
| Forms | **react-hook-form** + **zod** | 22 |
| Tables | **TanStack Table** | 22 |
| Charts | **Recharts** | 22 |
| Icons | **Lucide React** | 22 |
| E2E / AI debugging | **Playwright** (MCP-compatible, accessibility tree) | 22 |
| Browser logging | **Pino** (structured JSON) | 22 |

### Terminal Interfaces

| Concern | Technology | Doc |
|---------|-----------|-----|
| TUI framework | **Textual** (60 FPS, keyboard-first, SSH-compatible) | 27 |
| TUI in browser | **Textual Web** (same code, WebSocket, zero changes) | 27 |
| Rich text rendering | **Rich** (Textual dependency) | 27 |
| CLI framework | **Click** (groups + subcommands, `tree` command, Rich output) | 28 |

### Telegram

| Concern | Technology | Doc |
|---------|-----------|-----|
| Bot API (user interaction) | **aiogram v3** (async, Pydantic v2, FSM, middleware) | 25 |
| Client API (data acquisition) | **Telethon** or **Pyrogram** (MTProto, channel scraping) | 26 |

### AI / Agents (AI-First Profile)

| Concern | Technology | Doc |
|---------|-----------|-----|
| Agent framework | **PydanticAI** (v1.61+, `RunContext`, `output_type`, `TestModel`) | 41 |
| LLM provider (primary) | **Anthropic Claude** (Tier 1 tool calling, 200K context) | 24 |
| LLM testing | PydanticAI **TestModel** / **FunctionModel** (`ALLOW_MODEL_REQUESTS = False`) | 41 |
| Agent-to-tool protocol | **MCP** (Model Context Protocol, `mcp` SDK v1.26+) | 42 |
| Agent-to-agent protocol | **A2A** (Agent-to-Agent Protocol, `a2a-sdk`) | 42 |
| Vector store (Phase 3) | **pgvector** (PostgreSQL extension) | 41 |

### Deployment

| Concern | Technology | Doc |
|---------|-----------|-----|
| OS (bare metal) | **Ubuntu LTS** (22.04+) | 15 |
| Process management | **systemd** | 15 |
| Reverse proxy / TLS | **nginx** + **Let's Encrypt** (certbot) | 15 |
| Cloud (Azure) | **App Service** (Linux, native Python, no containers) | 16 |
| Azure database | **Azure Database for PostgreSQL Flexible Server** | 16 |
| Azure cache | **Azure Cache for Redis** (Premium, private endpoint) | 16 |
| Azure secrets | **Azure Key Vault** (RBAC, managed identity) | 16 |
| Azure frontend | **Azure Static Web Apps** | 16 |
| Azure monitoring | **Application Insights** + **Log Analytics** | 16 |
| Azure IaC | **Terraform** (Azure provider, state in Storage Account) | 16 |
| CI/CD | **GitHub Actions** (bare metal) or **Azure DevOps Pipelines** (Azure) | 12, 16 |

### Observability (Production)

| Concern | Technology | Doc |
|---------|-----------|-----|
| Metrics | **Prometheus** | 10 |
| Log aggregation | **Loki** (+ Promtail for shipping) | 10 |
| Dashboards / alerting | **Grafana** | 10 |

### Python Environment

| Project Type | Tool | Doc |
|-------------|------|-----|
| Web apps / APIs | **uv** (10-100x faster than pip, lockfiles) | 12 |
| Data / ML | **conda** (MKL-optimized numpy, CUDA/cuDNN pre-built) | 12 |

### Testing

| Concern | Technology | Doc |
|---------|-----------|-----|
| Test runner | **pytest** (async, markers, fixtures) | 11 |
| HTTP test client | **httpx** (`AsyncClient` + `ASGITransport`) | 11 |
| Coverage | **pytest-cov** | 11 |
| Mocking (external only) | **unittest.mock** / **AsyncMock** (only for services you don't operate) | 11 |
| Time mocking | **freezegun** | 11 |
| Security scanning | **bandit** (SAST), **pip-audit** / **safety** (deps), **detect-secrets** | 06 |

---

## Module Dependencies

### Cross-Reference Rule

**Core docs (01-16) never reference AI-First docs (40-46).** Dependency flows one way: AI-First docs reference core docs, never the reverse. This ensures a developer working on a Traditional Backend profile never encounters AI concepts.

| Source group | Can reference | Cannot reference |
|--------------|--------------|-----------------|
| Core (01-16) | Other core docs | Optional, AI-First |
| Optional Platform (20-28) | Core, other optional | AI-First |
| AI-First (40-48) | Core, optional, other AI-First | — (unrestricted) |

### Dependency Tree

```
┌─────────────────────────────────┐
│  41-agentic-pydanticai.md       │
│  (AI-First, implementation)     │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  40-agentic-architecture.md     │
│  (AI-First, conceptual)         │
└──────────┬──┬──────────────────┘
           │  │
    ┌──────┘  └──────────┐
    │                    │
    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐
│ 24-llm-integration│  │ 21-event-arch.md │
│   (optional)      │  │   (optional)     │
└──────────────────┘  └──────────────────┘

┌─────────────────────────────────┐
│  42-agent-first-infrastructure  │
│  (AI-First, independent of      │
│   40/41 — composable with them) │
└──────────┬──┬──────────────────┘
           │  │
    ┌──────┘  └──────┐
    │                │
    ▼                ▼
┌────────────┐  ┌────────────┐
│ 03-backend │  │ 05-auth.md │
│  (core)    │  │  (core)    │
└────────────┘  └────────────┘

┌─────────────────────────────────┐
│  44-multi-channel-gateway.md    │
│  (AI-First — channel delivery,  │
│   sessions, WebSocket push)     │
└──────────┬──┬──────────────────┘
           │  │
    ┌──────┘  └──────┐
    │                │
    ▼                ▼
┌────────────┐  ┌──────────────────────┐
│ 03-backend │  │ 25-telegram-bot.md   │
│  (core)    │  │  (optional, first    │
└────────────┘  │   channel adapter)   │
                └──────────────────────┘

┌─────────────────────────────────────┐
│  46-event-session-architecture.md   │
│  (AI-First — interactive sessions,  │
│   streaming, plans, memory, HITL)   │
└──────────┬──┬──────────┬──┬────────┘
           │  │          │  │
    ┌──────┘  │   ┌──────┘  └──────┐
    │         │   │                │
    ▼         ▼   ▼                ▼
┌──────────┐ ┌──────────┐  ┌──────────────────┐
│03-backend│ │21-events │  │40+41 agentic     │
│  (core)  │ │(optional)│  │  (AI-First)      │
└──────────┘ └──────────┘  └──────────────────┘

┌─────────────────────────────────────┐
│  48-agentic-project-context.md     │
│  (AI-First — persistent context,   │
│   PCD, agent contract, fractal     │
│   summarization)                   │
└──────────┬──┬──────────┬──────────┘
           │  │          │
    ┌──────┘  │   ┌──────┘
    │         │   │
    ▼         ▼   ▼
┌──────────┐ ┌──────────┐  ┌──────────────────┐
│40-agentic│ │41-pydantic│  │47-module-org     │
│  (AI)    │ │AI (AI)    │  │  (AI)            │
└──────────┘ └──────────┘  └──────────────────┘

┌─────────────────────────────────────┐
│  49-agentic-codebase-intelligence  │
│  (AI-First — Code Map, exemplars,  │
│   file manifests, coding agent     │
│   contract extension)              │
└──────────┬──┬──────────┬──────────┘
           │  │          │
    ┌──────┘  │   ┌──────┘
    │         │   │
    ▼         ▼   ▼
┌──────────┐ ┌──────────┐  ┌──────────────────┐
│48-project│ │47-module  │  │40-agentic        │
│ context  │ │  org      │  │  (AI)            │
└──────────┘ └──────────┘  └──────────────────┘

┌───────────────┐                       ┌───────────────┐
│ 22-frontend   │                       │ 20-data-layer │
│  (optional)   │                       │  (optional)   │
└───────┬───────┘                       └───────────────┘
        │
        ▼
┌───────────────────────┐
│ 23-typescript-stds.md │
│      (optional)       │
└───────────────────────┘
```

### Adoption Rules

If adopting 22-frontend-architecture.md, also adopt 23-typescript-coding-standards.md.
If adopting 41-agentic-pydanticai.md, also adopt 40-agentic-architecture.md, 24-llm-integration.md, and 21-event-architecture.md.
If adopting 42-agent-first-infrastructure.md, ensure 03-backend-architecture.md and 05-authentication.md are in place (both are core, so always present). Doc 42 is independent of 40/41 but composes naturally with them.
If adopting 44-multi-channel-gateway.md, ensure 03-backend-architecture.md and 25-telegram-bot-integration.md are in place. Doc 44 benefits from 40/41 for agent routing but can operate with any backend handler.
If adopting 46-event-session-architecture.md, also adopt 03-backend-architecture.md (core, always present), 21-event-architecture.md (event primitives), 40-agentic-architecture.md (agent concepts), and 41-agentic-pydanticai.md (PydanticAI implementation). Doc 46 composes with 44 (channels become event subscribers) and 43 (service factory accepts optional Session context) but does not require them.
If adopting any AI-First module (40-48), also adopt 47-agent-module-organization.md. Doc 47 defines the directory layout, naming conventions, and access control model that all other AI-First docs assume. Read it before building any agent.
If adopting 48-agentic-project-context.md, also adopt 40-agentic-architecture.md, 41-agentic-pydanticai.md, and 47-agent-module-organization.md. Doc 48 extends the dispatch loop from 40/41 with context assembly and agent contract hooks. The Summarization Agent follows the horizontal agent layout from 47. Required for all BFA projects running multi-mission workloads.
If adopting 49-agentic-codebase-intelligence.md, also adopt 48-agentic-project-context.md, 47-agent-module-organization.md, and 40-agentic-architecture.md. Doc 49 extends doc 48's context assembly with Layer 3 (Code Map), extends the PCD schema with exemplar fields, and adds a coding-specific agent contract. Recommended for all BFA projects with coding agents.

---

## When To Update This Standard

Update the standard when:
- A technology becomes unmaintained or deprecated
- Significantly better alternatives emerge with production maturity
- Security vulnerabilities require technology replacement
- Scale requirements exceed current technology capabilities

Do not update for:
- Personal preference
- Novelty or trendiness
- Minor performance improvements
- Single project edge cases

---

## Compliance

All new projects must follow Core standards (01-16). Optional and AI-First modules are adopted per project profile.

Existing projects should migrate toward compliance during major refactoring efforts.

Deviations require documented justification and approval. Approved deviations are tracked for potential standard updates.

---

## Quick Start

For a new project:

1. Choose your profile: **Traditional Backend** or **AI-First Platform (BFA)**
2. Apply all Core standards (01-16)
3. Review Optional Platform modules (20-28) against project requirements
4. If BFA profile, adopt AI-First modules (40-48)
5. Document which modules are adopted in project README
6. Follow the primitive identification process (02-primitive-identification.md)
7. Set up project structure per 03-backend-architecture.md
