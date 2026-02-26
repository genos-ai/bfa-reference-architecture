# 22 - Frontend Architecture (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic frontend architecture standard

---

## Module Status: Optional

This module is **optional**. Adopt when your project includes:
- Web frontend (React)
- Command-line interface

For backend-only services or API-only projects, this module is not required.

If adopting web frontend, also adopt **23-typescript-coding-standards.md**.

---

## Context

The core architecture mandates that clients are stateless presentation layers (P2) with no business logic (P1). This module defines how to build those thin clients for two surfaces: web browsers (React) and command lines (Python Click). It exists because even thin clients need consistent patterns for state management, API communication, and error handling — without them, each project makes different choices and the frontend becomes the least predictable part of the stack.

The web stack centers on React with Vite, TanStack Query for server state (caching, refetching, stale-while-revalidate), and Zustand for the minimal client-side state that remains (UI preferences, modal visibility). This separation was the key design decision — server state and client state have fundamentally different lifecycle and caching semantics, and mixing them in a single store is the most common source of frontend complexity.

The CLI uses Python Click because it offers explicit parameter handling, is well-documented for AI-assisted development, and integrates naturally with the Python backend ecosystem. Both clients consume the same backend API, ensuring feature parity and a single source of truth for all business logic. This module requires TypeScript coding standards (11) for web projects and follows all API conventions defined in backend architecture (03).

---

## Client Types

### Supported Clients

| Client | Purpose | Framework |
|--------|---------|-----------|
| Web | Primary user interface | React |
| CLI | Developer and power user interface | Python Click |

### Thin Client Mandate

All clients adhere to the thin client principle:
- No business logic
- No data validation beyond UI feedback
- No local data persistence (except caching)
- All state from backend APIs

---

## Web Client

### Framework: React with Vite

All web frontends use React with Vite as the build tool.

Rationale:
- Extensive AI training data for code assistance
- Large component ecosystem
- Fast development with Vite HMR
- TypeScript support

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
| Tables | TanStack Table |
| Charts | Recharts (general) |
| Icons | Lucide React |

### Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/          # shadcn/ui components
│   │   └── features/    # Feature-specific components
│   ├── hooks/           # Custom hooks
│   ├── lib/             # Utilities, API client
│   ├── pages/           # Route components
│   ├── stores/          # Zustand stores
│   └── types/           # TypeScript types
├── public/
├── index.html
├── package.json
├── tailwind.config.js
├── tsconfig.json
└── vite.config.ts
```

### State Management

**Server state** (data from backend): TanStack Query
- Automatic caching
- Background refetching
- Stale-while-revalidate
- Request deduplication

**Client state** (UI state): Zustand
- Minimal boilerplate
- Granular subscriptions for performance
- No Redux complexity

**Real-time data**: Direct WebSocket to Zustand store
- WebSocket updates write directly to Zustand
- Components subscribe to specific slices
- TanStack Query not used for real-time (avoids cache churn)

### API Client

Single API client module handles:
- Base URL configuration
- Authentication header injection
- Request/response transformation
- Error handling and retry
- Request cancellation

Use native fetch wrapped in utility functions.

### Error Handling

- Network errors: Toast notification, retry option
- 401 errors: Redirect to login
- 400/422 errors: Display field-level validation
- 500 errors: Generic error message with error ID

Never display raw error messages to users. Map error codes to user-friendly messages.

---

## CLI Client

### Framework: Python Click

CLI applications use Click with Rich for output formatting.

Rationale:
- Consistent with backend Python
- Excellent AI code assistance
- Rich provides professional terminal output
- Click handles argument parsing robustly

### Technology Stack

| Concern | Solution |
|---------|----------|
| Framework | Click |
| HTTP Client | httpx (async) |
| Output | Rich |
| Configuration | YAML + environment variables |
| Authentication | API key stored in config file |

### Project Structure

```
cli/
├── src/
│   └── cli_name/
│       ├── __init__.py
│       ├── main.py          # Entry point
│       ├── commands/        # Command modules
│       ├── api/             # API client
│       ├── config/          # Configuration
│       └── utils/           # Utilities
├── setup.py
└── requirements.txt
```

### Command Structure

Commands organized by domain with subcommands:

```bash
cli auth login
cli project create
cli project list
cli data export --format csv
```

### Standard Options

All CLIs include these standard options:
- `--verbose` / `-v`: Enable verbose output
- `--debug`: Enable debug mode with full stack traces
- `--help`: Show help

### Output Formatting

- Success: Green text, clear confirmation
- Error: Red text, error message, suggestion if applicable
- Data: Tables for lists, key-value for details
- Progress: Progress bars for long operations

### Configuration

Configuration stored in `~/.{cli-name}/config.yaml`:
- API endpoint
- API key
- Default project
- User preferences

### Offline Behavior

CLIs fail fast when offline. No offline mode. Clear error message directs user to check connection.

---

## Cross-Client Consistency

### API Contract

All clients consume the same backend API. No client-specific endpoints.

API changes tested against all clients before deployment.

### Feature Parity

Core features available in all clients. Client-specific features documented.

| Feature | Web | CLI |
|---------|-----|-----|
| Full functionality | Yes | Yes |
| Real-time updates | Yes | Limited |
| Data visualization | Yes | Text |
| Bulk operations | Limited | Yes |

### Authentication

All clients use API keys for backend authentication. API key acquisition:
- Web: Login flow, key displayed in settings
- CLI: Login command, key stored in config

---

## AI-Assisted Debugging

### Standard: Playwright MCP

All frontend projects use Playwright for AI-assisted debugging.

Rationale:
- CLI-native, no browser extensions required
- Accessibility tree output optimized for LLMs
- Works in CI/CD, headless environments
- Scriptable and reproducible

### Structured Error Logging

Frontend apps output errors in JSON format for AI consumption:

| Tool | Purpose |
|------|---------|
| Pino | Structured JSON logging in browser |
| react-error-boundary | Catch and log React errors as JSON |
| vite-plugin-checker | Real-time TypeScript errors in terminal |

### Test Reporters

Configure JSON output for machine-readable test results:

```typescript
// playwright.config.ts
export default defineConfig({
  reporter: [
    ['list'],
    ['json', { outputFile: 'test-results.json' }]
  ]
});
```

---

## Adoption Checklist

When adopting this module:

### Web Frontend
- [ ] Set up Vite + React project
- [ ] Configure TypeScript strict mode
- [ ] Install Tailwind CSS and shadcn/ui
- [ ] Set up TanStack Query
- [ ] Create API client module
- [ ] Configure error boundaries
- [ ] Set up Playwright for testing

### CLI
- [ ] Set up Click project structure
- [ ] Implement standard options (--verbose, --debug)
- [ ] Create API client with httpx
- [ ] Implement configuration management
- [ ] Set up Rich for output formatting
