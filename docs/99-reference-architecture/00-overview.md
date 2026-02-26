# Architecture Standards Overview

*Version: 2.4.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 2.4.0 (2026-02-26): Added 31-event-session-architecture.md for event-driven sessions, streaming coordinator, plan management, memory architecture, approval gates; updated dependency tree
- 2.3.0 (2026-02-24): Added 29-multi-channel-gateway.md for channel adapters, session management, real-time push, gateway security; updated 01 with P8 Secure by Default
- 2.2.0 (2026-02-24): Added 28-tui-architecture.md for interactive terminal interface (Textual)
- 2.1.0 (2026-02-20): Added 27-agent-first-infrastructure.md for MCP, A2A, agent identity, intent APIs, agent-discoverable endpoints
- 2.0.0 (2026-02-19): Consolidated agentic docs — trimmed 25 to framework-agnostic concepts, rewrote 26 with PydanticAI-native patterns, archived research-25
- 1.9.0 (2026-02-18): Split agentic docs into 25 (conceptual) and 26 (PydanticAI implementation)
- 1.8.0 (2026-02-18): Added 25-agentic-architecture.md for agentic AI systems (agents, orchestration, tools, memory)
- 1.7.0 (2026-02-18): Added 23-telegram-client-integration.md for Telegram Client API (MTProto)
- 1.6.0 (2026-02-18): Renumbered docs; moved deployment to 21-22; added 22-deployment-azure.md
- 1.5.0 (2026-02-13): Added 20-telegram-bot-integration.md for Telegram bot integration (aiogram v3)
- 1.4.0 (2025-01-29): Added data/ directory structure for file-based data storage
- 1.3.0 (2025-01-29): Added Python environment management guide (uv vs conda) to 13-development-workflow.md
- 1.2.0 (2025-01-29): Added 16-testing-standards.md with comprehensive testing guidance
- 1.1.0 (2025-01-27): Added 15-project-template.md with complete project structure
- 1.0.0 (2025-01-27): Initial generic architecture standards

---

## Purpose

This document set defines architecture standards for software projects. It is prescriptive, not advisory. These are decisions, not options.

When a technology choice no longer serves the standard, the standard is updated. Individual projects do not deviate; the standard evolves.

---

## Context

Architectural decisions made inconsistently across projects create compounding costs — different teams reinvent the same solutions, onboarding takes longer, and AI code assistants produce inconsistent output without shared conventions. This document set exists to make those decisions once, document them prescriptively, and apply them uniformly.

The structure separates Core standards (which apply to every project unconditionally) from Optional modules (which are adopted per project need). This lets teams skip irrelevant complexity — a backend-only API doesn't need frontend standards — while ensuring that when a capability is adopted, it follows the same patterns everywhere. Optional modules declare their dependencies explicitly, so adopting one module tells you exactly what else you need.

Each document in this set is self-contained enough to be read independently, but they form a coherent whole. Core Principles (01) define the non-negotiable mandates. Backend Architecture (03) and Module Structure (04) define how code is organized. Coding Standards (10, 11), Testing (16), and Workflow (13) define how code is written and shipped. Security (17), Data Protection (18), and Authentication (09) define how it is secured. Deployment (21, 22) defines how it runs. Optional modules — Data Layer (05), Events (06), Frontend (07), LLM (08), Telegram (20, 23), Agentic AI (25, 26), Agent-First Infrastructure (27), TUI (28), Multi-Channel Gateway (29), AI-First Interface Design (30), Event-Driven Sessions (31) — extend the core when projects need those capabilities.

---

## Structure: Core + Optional Modules

Standards are organized into **Core** (always apply) and **Optional** (adopt as needed) modules.

### Core Standards

These apply to all projects without exception:

| Document | Purpose |
|----------|---------|
| 01-core-principles.md | Non-negotiable architectural mandates |
| 02-primitive-identification.md | Identifying the system's fundamental data type |
| 03-backend-architecture.md | Backend framework, service layer, API design |
| 04-module-structure.md | Module organization and inter-module communication |
| 09-authentication.md | Authentication and authorization |
| 17-security-standards.md | Application security (OWASP, cryptography, input handling) |
| 18-data-protection.md | Data protection and privacy (PII, GDPR, retention) |
| 10-python-coding-standards.md | Python file organization, imports, CLI, error handling |
| 12-observability.md | Logging, monitoring, debugging, alerting |
| 13-development-workflow.md | Git workflow, CI/CD, testing, versioning |
| 14-error-codes.md | Error code registry, client handling guide |
| 15-project-template.md | Standard project directory structure |
| 16-testing-standards.md | Test organization, fixtures, coverage |
| 19-background-tasks.md | Background tasks and scheduling (Taskiq) |
| 21-deployment-bare-metal.md | Self-hosted deployment (Ubuntu, systemd, nginx) |
| 22-deployment-azure.md | Azure managed services deployment |

### Optional Modules

Adopt these based on project requirements:

| Document | When to Adopt |
|----------|---------------|
| 05-data-layer.md | Projects requiring databases beyond basic PostgreSQL |
| 06-event-architecture.md | Projects with async processing, real-time updates |
| 07-frontend-architecture.md | Projects with web frontends |
| 08-llm-integration.md | Projects using LLM/AI capabilities |
| 11-typescript-coding-standards.md | Projects with TypeScript/React frontends |
| 20-telegram-bot-integration.md | Projects with Telegram bot interfaces |
| 23-telegram-client-integration.md | Projects needing channel scraping, history access (MTProto) |
| 25-agentic-architecture.md | Agentic AI conceptual architecture — framework-agnostic (phases, principles, orchestration patterns, AgentTask primitive) |
| 26-agentic-pydanticai.md | Agentic AI implementation using PydanticAI (coordinator, agents, middleware, testing, database schema). Read 25 first. |
| 27-agent-first-infrastructure.md | Agent-first infrastructure — MCP servers, A2A protocol, agent identity, intent APIs, agent-discoverable endpoints. Independent of 25/26. |
| 28-tui-architecture.md | Terminal User Interface — interactive agent sessions, real-time monitoring, approvals, Textual + Textual Web |
| 29-multi-channel-gateway.md | Multi-channel delivery — channel adapters, session management, real-time WebSocket push, DM pairing, gateway security |
| 30-ai-first-interface-design.md | AI-first interface design — adapter registry, self-describing APIs, intent/planning APIs, service factory, CLI AI patterns. Requires 03, 04, 14, 27. |
| 31-event-session-architecture.md | Event-driven session architecture — session model, event bus, streaming coordinator, plan management as mutable DAGs, memory architecture (episodic/semantic/procedural), approval and escalation with unified responder pattern, cost tracking, observability. Requires 03, 06, 25, 26. |

---

## Scope

### In Scope

- Python backend services with thin clients
- Web frontends (React)
- Terminal user interfaces (Textual)
- Command-line interfaces
- Data pipelines and analytics
- General web applications

### Out of Scope

- Mobile-native applications
- Desktop applications (Electron/Tauri)
- Embedded systems
- Gaming applications

### Optional Scope (via modules)

- AI/LLM integration
- Agentic AI systems (autonomous agents, orchestration, tools, memory)
- Agent-first infrastructure (MCP, A2A, agent identity, intent APIs)
- Multi-channel delivery (Telegram, Slack, Discord, WebSocket gateway)
- Real-time data streaming
- Time-series data processing
- Event-driven architectures
- Event-driven session architecture (persistent sessions, streaming coordinators, plan management, agent memory)

---

## Core Philosophy

### Backend-First Architecture

All business logic resides in the backend. Clients are presentation layers only. No business rules, validation logic, or data transformation occurs in clients.

Benefits:
- Single source of truth
- Consistent behavior across all client types
- Security logic centralized
- Easier testing and debugging
- New clients require only API consumption

### Thin Client Mandate

Clients perform three functions only:
1. Present data received from the backend
2. Capture user input and send to backend
3. Handle client-specific UI/UX concerns

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

## Adopting Optional Modules

### Decision Criteria

| Module | Adopt When |
|--------|------------|
| 05-data-layer.md | Need time-series, analytics, or advanced caching |
| 06-event-architecture.md | Need async processing, WebSocket, or message queues |
| 07-frontend-architecture.md | Building a web UI |
| 08-llm-integration.md | Integrating AI/LLM capabilities |
| 11-typescript-coding-standards.md | Building React frontend |
| 20-telegram-bot-integration.md | Building Telegram bot interface |
| 23-telegram-client-integration.md | Need channel scraping, message history, or autonomous Telegram access |
| 25-agentic-architecture.md | Agentic AI conceptual architecture — framework-agnostic (phases, principles, patterns) |
| 26-agentic-pydanticai.md | Agentic AI implementation using PydanticAI. Read 25 first. |
| 27-agent-first-infrastructure.md | Exposing platform to external agents (MCP, A2A), agent identity, intent APIs |
| 28-tui-architecture.md | Interactive terminal interface (Textual) for agent sessions, monitoring, approvals |
| 29-multi-channel-gateway.md | Delivering agent interactions through multiple messaging channels (Telegram, Slack, Discord, WebSocket) with cross-channel sessions |
| 30-ai-first-interface-design.md | Making services consumable by AI agents (Cursor, Claude Code, external orchestrators) alongside human clients |
| 31-event-session-architecture.md | Interactive conversations, streaming agent responses, multi-step plans with approval gates, long-running autonomous tasks, multi-channel sessions |

### Module Dependencies

```
        ┌─────────────────────────────────┐
        │  26-agentic-pydanticai.md       │
        │  (optional, implementation)     │
        └──────────────┬──────────────────┘
                       │
                       ▼
        ┌─────────────────────────────────┐
        │  25-agentic-architecture.md     │
        │  (optional, conceptual)         │
        └──────────┬──┬──────────────────┘
                   │  │
        ┌──────────┘  └──────────┐
        │                        │
        ▼                        ▼
┌─────────────────────┐  ┌─────────────────────┐
│ 08-llm-integration  │  │ 06-event-arch.md    │
│    (optional)       │  │    (optional)       │
└─────────────────────┘  └─────────────────────┘

┌─────────────────────────────────┐
│  27-agent-first-infrastructure  │
│  (optional, independent of      │
│   25/26 — composable with them) │
└──────────┬──┬──────────────────┘
           │  │
    ┌──────┘  └──────┐
    │                │
    ▼                ▼
┌────────────┐  ┌────────────┐
│ 03-backend │  │ 09-auth.md │
│  (core)    │  │  (core)    │
└────────────┘  └────────────┘

┌─────────────────────────────────┐
│  29-multi-channel-gateway.md   │
│  (optional — channel delivery, │
│   sessions, WebSocket push)    │
└──────────┬──┬──────────────────┘
           │  │
    ┌──────┘  └──────┐
    │                │
    ▼                ▼
┌────────────┐  ┌──────────────────────┐
│ 03-backend │  │ 20-telegram-bot.md   │
│  (core)    │  │  (optional, first    │
└────────────┘  │   channel adapter)   │
                └──────────────────────┘

┌─────────────────────────────────────┐
│  31-event-session-architecture.md   │
│  (optional — interactive sessions,  │
│   streaming, plans, memory, HITL)   │
└──────────┬──┬──────────┬──┬────────┘
           │  │          │  │
    ┌──────┘  │   ┌──────┘  └──────┐
    │         │   │                │
    ▼         ▼   ▼                ▼
┌──────────┐ ┌──────────┐  ┌──────────────────┐
│03-backend│ │06-events │  │25+26 agentic     │
│  (core)  │ │(optional)│  │    (optional)     │
└──────────┘ └──────────┘  └──────────────────┘

┌───────────────┐                       ┌───────────────┐
│ 07-frontend   │                       │ 05-data-layer │
│  (optional)   │                       │  (optional)   │
└───────┬───────┘                       └───────────────┘
        │
        ▼
┌───────────────────────┐
│ 11-typescript-stds.md │
│      (optional)       │
└───────────────────────┘
```

If adopting 07-frontend-architecture.md, also adopt 11-typescript-coding-standards.md.
If adopting 26-agentic-pydanticai.md, also adopt 25-agentic-architecture.md, 08-llm-integration.md, and 06-event-architecture.md.
If adopting 27-agent-first-infrastructure.md, ensure 03-backend-architecture.md and 09-authentication.md are in place (both are core, so always present). Doc 27 is independent of 25/26 but composes naturally with them.
If adopting 29-multi-channel-gateway.md, ensure 03-backend-architecture.md and 20-telegram-bot-integration.md are in place. Doc 29 benefits from 25/26 for agent routing but can operate with any backend handler.
If adopting 31-event-session-architecture.md, also adopt 03-backend-architecture.md (core, always present), 06-event-architecture.md (event primitives), 25-agentic-architecture.md (agent concepts), and 26-agentic-pydanticai.md (PydanticAI implementation). Doc 31 composes with 29 (channels become event subscribers) and 30 (service factory accepts optional Session context) but does not require them.

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

All new projects must follow Core standards. Optional modules are adopted per project needs.

Existing projects should migrate toward compliance during major refactoring efforts.

Deviations require documented justification and approval. Approved deviations are tracked for potential standard updates.

---

## Quick Start

For a new project:

1. Apply all Core standards
2. Review Optional modules against project requirements
3. Document which Optional modules are adopted in project README
4. Follow the primitive identification process (02-primitive-identification.md)
5. Set up project structure per 03-backend-architecture.md
