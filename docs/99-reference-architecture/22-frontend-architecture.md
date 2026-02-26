# 22 - Web Frontend Architecture (Optional Module)

*Version: 2.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 2.0.0 (2026-02-26): Narrowed scope to web frontend only; removed CLI section (CLI patterns defined in 08-python-coding-standards.md and demonstrated by root entry scripts); renamed from "Frontend Architecture" to "Web Frontend Architecture"
- 1.0.0 (2025-01-27): Initial generic frontend architecture standard

---

## Module Status: Optional

This module is **optional**. Adopt when your project includes a web frontend (React).

For backend-only services, API-only projects, or terminal-only interfaces, this module is not required.

If adopting, also adopt **23-typescript-coding-standards.md**.

**CLI patterns** are covered by **08-python-coding-standards.md** (Click, `--verbose`/`--debug`, Rich output, `--options` not subcommands). TUI patterns are covered by **27-tui-architecture.md** (Textual).

---

## Context

The core architecture mandates that clients are stateless presentation layers (P2) with no business logic (P1). This module defines how to build the web client following those principles.

The web stack centers on React with Vite, TanStack Query for server state (caching, refetching, stale-while-revalidate), and Zustand for the minimal client-side state that remains (UI preferences, modal visibility). This separation was the key design decision — server state and client state have fundamentally different lifecycle and caching semantics, and mixing them in a single store is the most common source of frontend complexity.

This module requires TypeScript coding standards (23) and follows all API conventions defined in backend architecture (03).

---

## Thin Client Mandate

The web frontend adheres to the thin client principle:
- No business logic
- No data validation beyond UI feedback
- No local data persistence (except caching)
- All state from backend APIs

The backend is the single source of truth. The web client renders what the backend tells it.

---

## Technology Stack

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

### Rationale

React with Vite is chosen because:
- Extensive AI training data for code assistance
- Large component ecosystem
- Fast development with Vite HMR
- TypeScript support

---

## Project Structure

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

---

## State Management

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

---

## API Client

Single API client module handles:
- Base URL configuration
- Authentication header injection
- Request/response transformation
- Error handling and retry
- Request cancellation

Use native fetch wrapped in utility functions.

---

## Error Handling

- Network errors: Toast notification, retry option
- 401 errors: Redirect to login
- 400/422 errors: Display field-level validation
- 500 errors: Generic error message with error ID

Never display raw error messages to users. Map error codes to user-friendly messages.

---

## Cross-Client Consistency

All clients (web, CLI, TUI, Telegram) consume the same backend API. No client-specific endpoints.

| Principle | Rule |
|-----------|------|
| API contract | All clients hit the same endpoints |
| Feature parity | Core features available in all clients |
| Authentication | API keys for backend authentication |
| Error codes | Backend error codes mapped to client-appropriate messages |

API changes tested against all active clients before deployment.

---

## AI-Assisted Debugging

### Standard: Playwright MCP

All web frontend projects use Playwright for AI-assisted debugging.

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

- [ ] Set up Vite + React project
- [ ] Configure TypeScript strict mode
- [ ] Install Tailwind CSS and shadcn/ui
- [ ] Set up TanStack Query for server state
- [ ] Set up Zustand for client state
- [ ] Create API client module
- [ ] Configure error boundaries (react-error-boundary)
- [ ] Set up Playwright for testing
- [ ] Configure Pino for structured browser logging
- [ ] Set up WebSocket → Zustand for real-time data

---

## Related Documentation

- [23-typescript-coding-standards.md](23-typescript-coding-standards.md) — TypeScript coding standards (required)
- [03-backend-architecture.md](03-backend-architecture.md) — API conventions consumed by the frontend
- [09-error-codes.md](09-error-codes.md) — Error code registry for client-side mapping
- [01-core-principles.md](01-core-principles.md) — Thin client mandate (P1, P2)
- [27-tui-architecture.md](27-tui-architecture.md) — Terminal UI alternative (Textual + Textual Web)
