# 23 - TypeScript Coding Standards (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic TypeScript coding standards

---

## Module Status: Optional

This module is **optional**. Adopt when your project includes a React web frontend.

This module is a dependency of **22-frontend-architecture.md** for web projects.

---

## Context

When the architecture includes a React web frontend (22-frontend-architecture), TypeScript coding standards become mandatory. This module exists because React's flexibility means two developers will structure the same application completely differently without shared conventions — different state management approaches, different component patterns, different file organization.

The key design decision is strict separation of state concerns: TanStack Query owns server state (API responses, caching, refetching), Zustand owns client state (UI preferences, ephemeral UI data), and react-hook-form owns form state (validation, dirty tracking). Mixing these in a single store or using the wrong tool for each creates the complexity that makes React applications hard to maintain.

File size limits are tighter than the backend (300 lines for components, 150 for hooks) because large React components are almost always doing too many things. Tailwind CSS is the only approved styling approach — no CSS modules, no styled-components, no inline styles — because a single styling system eliminates the "which approach do I use?" question and keeps AI code assistance consistent. This module complements the Python coding standards (08) for backend development.

---

## Scope

This document defines coding standards for React web frontends. It complements the Python Development Standards and Architecture Standards.

---

## File Organization

### Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # Reusable UI primitives (shadcn/ui)
│   │   └── features/        # Feature-specific components
│   │       └── {feature}/
│   │           ├── {Feature}.tsx
│   │           ├── {Feature}.test.tsx
│   │           └── index.ts
│   ├── hooks/               # Custom React hooks
│   ├── lib/                 # Utilities, API client, helpers
│   ├── pages/               # Route components (one per route)
│   ├── stores/              # Zustand stores
│   ├── types/               # TypeScript type definitions
│   └── config/              # Frontend configuration
├── public/
├── index.html
├── package.json
├── tailwind.config.js
├── tsconfig.json
└── vite.config.ts
```

### File Naming

| Type | Convention | Example |
|------|------------|---------|
| Components | PascalCase | `OrderList.tsx` |
| Hooks | camelCase with `use` prefix | `useWebSocket.ts` |
| Utilities | camelCase | `formatCurrency.ts` |
| Types | PascalCase | `UserTypes.ts` |
| Stores | camelCase with `Store` suffix | `userStore.ts` |
| Tests | Same name with `.test.tsx` | `OrderList.test.tsx` |

### File Size Limits

- Components: **300 lines maximum**
- Hooks: **150 lines maximum**
- Utilities: **200 lines maximum**
- Stores: **200 lines maximum**

If a file exceeds these limits, split it into smaller, focused modules.

---

## Component Standards

### Component Structure

Every component follows this order:

1. Imports
2. Types/interfaces
3. Component function
4. Styles (if using CSS-in-JS)

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Component | PascalCase | `UserProfile` |
| Props interface | ComponentName + Props | `UserProfileProps` |
| Event handlers | handle + Event | `handleClick`, `handleSubmit` |
| Boolean props | is/has/should prefix | `isLoading`, `hasError` |
| Callbacks | on + Action | `onSelect`, `onChange` |

### Props

- Define explicit interface for all props
- Use destructuring in function signature
- Provide default values where sensible
- Document complex props with JSDoc

### Component Organization

Group related components in feature folders:

```
features/
└── users/
    ├── UserProfile.tsx
    ├── UserList.tsx
    ├── UserForm.tsx
    ├── hooks/
    │   └── useUsers.ts
    └── index.ts           # Public exports only
```

---

## State Management

### Server State: TanStack Query

Use TanStack Query for all data fetched from backend:

- Configure staleTime based on data freshness needs
- Use queryKey arrays consistently
- Implement error boundaries for query failures
- Never store fetched data in local state

### Client State: Zustand

Use Zustand for UI state that doesn't come from server:

- One store per domain (userStore, uiStore)
- Use selectors with equality functions for performance
- Keep stores flat, avoid deep nesting
- Never duplicate server state in Zustand

### Real-Time State

WebSocket data goes directly to Zustand:

- Dedicated store for real-time data
- Granular subscriptions to prevent re-renders
- Clear separation from TanStack Query data

### State Location Decision

| State Type | Location |
|------------|----------|
| Server data (fetched) | TanStack Query |
| Real-time data (WebSocket) | Zustand |
| Form state | react-hook-form |
| UI state (modals, tabs) | Zustand or useState |
| URL state | Router |

---

## TypeScript Standards

### Strict Mode

TypeScript strict mode is mandatory:

```json
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true
  }
}
```

### Type Definitions

- Define types in `types/` directory for shared types
- Co-locate component-specific types with component
- Export types from barrel files
- Prefer interfaces for object shapes
- Prefer type aliases for unions and primitives

### Avoid `any`

The `any` type is forbidden except:

- Third-party library interop (with TODO comment)
- Temporary during development (with TODO comment)

All `any` usages must include comment explaining why and plan to remove.

### Type vs Interface

| Use | When |
|-----|------|
| `interface` | Object shapes, component props |
| `type` | Unions, intersections, primitives, mapped types |

---

## Error Handling

### Error Boundaries

Wrap feature sections with error boundaries:

- Catch rendering errors
- Display fallback UI
- Log errors for debugging
- Provide retry mechanism

### API Errors

Handle at the hook/service level:

- TanStack Query's error state for fetch errors
- Transform backend errors to user-friendly messages
- Never display raw error messages to users

### Form Errors

Handle with react-hook-form + zod:

- Validate on blur and submit
- Display inline field errors
- Summary for form-level errors

---

## Styling Standards

### Tailwind CSS

Use Tailwind for all styling:

- No inline styles (except dynamic values)
- No CSS modules
- No styled-components
- Use `cn()` utility for conditional classes

### Class Organization

Order Tailwind classes consistently:

1. Layout (flex, grid, position)
2. Sizing (w, h, p, m)
3. Typography (text, font)
4. Colors (bg, text, border)
5. Effects (shadow, opacity)
6. Transitions

### Responsive Design

Mobile-first approach:

- Start with mobile styles
- Add breakpoints for larger screens: `sm:`, `md:`, `lg:`
- Test on actual devices, not just browser resize

### Dark Mode

Support dark mode via Tailwind:

- Use `dark:` prefix for dark variants
- Store preference in localStorage
- Respect system preference by default

---

## Performance

### Re-render Prevention

- Use `React.memo()` for expensive components
- Use `useMemo()` for expensive computations
- Use `useCallback()` for callbacks passed to children
- Use Zustand selectors with equality functions

### Code Splitting

- Lazy load routes with `React.lazy()`
- Lazy load heavy components (charts, editors)
- Use Suspense with loading fallbacks

### Bundle Size

- Monitor bundle size in CI
- Avoid importing entire libraries (use tree-shaking)
- Analyze with `vite-bundle-visualizer`

---

## Testing

### Test Location

Tests co-located with components:

```
UserProfile.tsx
UserProfile.test.tsx
```

### What to Test

| Priority | What |
|----------|------|
| High | User interactions, form submissions |
| High | Conditional rendering logic |
| Medium | Component integration |
| Low | Snapshot tests (use sparingly) |

### Testing Tools

- Vitest for test runner
- React Testing Library for component tests
- MSW for API mocking

### Test Naming

Describe behavior, not implementation:

```
- displays loading state while fetching
- shows error message when request fails
- submits form with valid data
```

---

## Imports

### Import Order

Organize imports in groups:

1. React and framework imports
2. Third-party libraries
3. Internal absolute imports
4. Relative imports
5. Type imports

Separate groups with blank line.

### Path Aliases

Use path aliases for cleaner imports:

```typescript
// vite.config.ts / tsconfig.json
{
  "paths": {
    "@/*": ["./src/*"]
  }
}

// Usage
import { Button } from "@/components/ui/button"
import { useUsers } from "@/hooks/useUsers"
```

### Barrel Exports

Use index.ts files for public API:

- Export only public components/functions
- Keep internal implementation details private
- One barrel per feature folder

---

## Configuration

### No Hardcoded Values

All configuration comes from:

- Environment variables (`import.meta.env`)
- Configuration files
- Backend API

Never hardcode:

- API URLs
- Feature flags
- Magic numbers
- Timeouts

### Environment Variables

Prefix all env vars with `VITE_`:

```
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

Access via typed config object, not direct `import.meta.env` access.

---

## Accessibility

### Minimum Requirements

- Semantic HTML elements
- ARIA labels where needed
- Keyboard navigation
- Focus management
- Color contrast compliance

### Testing

- Use axe-core for automated checks
- Manual keyboard navigation testing
- Screen reader testing for critical flows

---

## Anti-Patterns to Avoid

- Business logic in components (belongs in backend)
- Direct DOM manipulation
- Prop drilling beyond 2 levels (use context or store)
- Inline styles for static values
- `any` type without justification
- Importing entire libraries
- Storing server data in useState
- Missing loading/error states
- Hardcoded strings (use constants or i18n)
- Console.log in production code
