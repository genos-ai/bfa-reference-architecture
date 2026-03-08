# 27 - TUI Architecture (Optional Module)

*Version: 2.0.0*
*Author: Architecture Team*
*Created: 2026-02-24*

## Changelog

- 2.0.0 (2026-02-26): Moved from AI-First (45) to Optional Platform (27); stripped AI-specific panels; generalized as framework reference for any interactive terminal application
- 1.0.0 (2026-02-24): Initial TUI architecture standard

---

## Module Status: Optional

This module is **optional**. Adopt when your project needs:
- An interactive terminal interface beyond one-shot CLI commands
- Real-time streaming of data or events from the backend
- A persistent session with state that accumulates over time
- A power user interface that works over SSH and in low-bandwidth environments
- A browser-accessible terminal UI without building a separate React frontend

**Dependencies**: This module requires **22-frontend-architecture.md** (thin client principles).

For command-based, one-shot operations (automation, scripting, CI/CD), use the CLI (Click) defined in 28-cli-architecture.md. Adopt this module when the user needs a persistent, interactive session with real-time feedback.

---

## Context

The existing architecture defines two terminal-facing client types: the CLI (Click) for command-based operations and the Telegram bot for mobile chat. Neither serves the interactive, session-based workflow where the user maintains a continuous conversation with the backend, watches operations unfold in real-time, takes action on events as they arrive, and monitors multiple concurrent processes.

A TUI fills this gap. It is a persistent, interactive terminal application that stays open for the duration of a working session. It is keyboard-first, works over SSH, renders at 60 FPS, and — critically — the same codebase can be served in a browser via Textual Web with zero code changes.

### How TUI differs from CLI

| Aspect | CLI (Click) | TUI (Textual) |
|--------|------------|---------------|
| Interaction model | Command → output → done | Persistent session, continuous interaction |
| State | Stateless — each invocation is independent | Stateful — session persists, context accumulates |
| Real-time | No — waits for command to complete | Yes — streams data as it arrives |
| Concurrent tasks | Run multiple commands in separate terminals | Tabs within one application |
| Use case | Automation, scripts, CI/CD, system admin | Interactive work, monitoring, dashboards |

Both are needed. They serve different purposes and coexist.

---

## Technology Stack

### Framework: Textual

**Package:** `textual` (latest stable)

Textual is chosen because:
- Built by the Pydantic/Rich team — same ecosystem as the backend and CLI
- Python — no language boundary between TUI and backend
- React-inspired component hierarchy with CSS styling
- Reactive data binding — UI updates automatically when data changes
- Background workers keep the UI responsive during long operations
- 60 FPS rendering, 5-10x faster than curses
- Works over SSH
- **Textual Web** — same code runs in the browser via WebSocket with zero changes

### Supporting Libraries

| Concern | Solution |
|---------|----------|
| Framework | Textual |
| Rich text rendering | Rich (Textual dependency) |
| HTTP client | httpx (async) |
| WebSocket client | websockets or httpx-ws |
| Configuration | YAML + environment variables (same as CLI) |
| Authentication | API key stored in config file (same as CLI) |

### Textual Web

Textual Web serves the same TUI application in a browser via secure WebSocket. This eliminates the need for a React frontend for technical users:

- No separate codebase to maintain
- No TypeScript, no build step, no npm
- Same keyboard shortcuts, same layout, same behavior
- Accessible via URL — no installation needed for browser users
- Can run behind nginx (same deployment model as the backend)

Use Textual Web as the browser interface for internal/technical users. Build React only if you need a polished public-facing UI for non-technical users.

---

## Thin Client Mandate

The TUI follows the same thin client principles as all other clients per **01-core-principles.md P1/P2**:

- **No business logic** — all processing happens in the backend
- **No data validation** beyond UI feedback — the backend validates everything
- **No local data persistence** — all state comes from the backend API, except ephemeral UI state (which tab is active, scroll position)
- **All state from backend APIs** — the TUI renders what the backend tells it

The TUI is a presentation layer. A sophisticated one — with real-time streaming, tabs, and interactive panels — but still just a presentation layer.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     TUI Application (Textual)                │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Tab 1   │  │  Tab 2   │  │  Tab 3   │  │  Tab N   │   │
│  │ Primary  │  │ Monitor  │  │ Browse   │  │ Custom   │   │
│  │ Panel    │  │ Dashboard│  │ / Search │  │ Panel    │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │              │         │
│       └──────────────┴──────────────┴──────────────┘         │
│                              │                               │
│  ┌───────────────────────────┴────────────────────────────┐  │
│  │                    Status Bar                           │  │
│  │  Connection: ● │ Session: active │ Items: 42            │  │
│  └────────────────────────────────────────────────────────┘  │
│                              │                               │
│                    ┌─────────┴─────────┐                     │
│                    │    API Client      │                     │
│                    │  REST + WebSocket  │                     │
│                    └─────────┬─────────┘                     │
└──────────────────────────────┼───────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │   Backend (FastAPI)  │
                    │   X-Frontend-ID: tui │
                    └─────────────────────┘
```

### Connection Model

The TUI maintains two connections to the backend:

1. **REST (httpx)** — for request-response operations: submit data, query state, browse records
2. **WebSocket** — for real-time streaming: live updates, event notifications, progress tracking

The WebSocket subscribes to events relevant to the current session. When the user switches tabs, subscriptions update. When the TUI disconnects, it reconnects with exponential backoff per **21-event-architecture.md**.

### X-Frontend-ID

The TUI sends `X-Frontend-ID: tui` with every request per **10-observability.md**. This enables:
- Log filtering by source (`logs/system.jsonl` with `source="tui"`)
- Per-frontend metrics in dashboards
- Debugging TUI-specific issues

---

## Panel Architecture

The TUI is organized into panels, composed into tabs. Each panel is a Textual Widget that subscribes to specific data streams. Concrete panels are application-specific — define them based on what your application does.

### Panel Pattern

Every panel follows this structure:

```python
from textual.widgets import Static
from textual.reactive import reactive

class DashboardPanel(Static):
    """A panel that displays live data from the backend."""

    data: reactive[dict] = reactive({})

    def on_mount(self) -> None:
        """Subscribe to relevant WebSocket events on mount."""
        self.app.subscribe("dashboard.updated", self._on_update)

    def _on_update(self, event: dict) -> None:
        """Handle incoming data from WebSocket."""
        self.data = event

    def render(self) -> str:
        """Render the panel content."""
        return f"Items: {len(self.data)}"
```

### Example Panel Types

| Panel Type | Purpose | Data Source |
|-----------|---------|-------------|
| **Interactive Chat** | Conversational interface with backend services | REST POST + WebSocket stream |
| **Live Dashboard** | Real-time metrics, status indicators | WebSocket subscription |
| **Record Browser** | Search and browse data with pagination | REST GET with cursor pagination |
| **Log Viewer** | Streaming log output | WebSocket subscription |
| **Action Panel** | Approve/reject/confirm operations | REST POST triggered by keyboard shortcut |
| **Status Bar** | Session-level summary metrics | WebSocket subscription (persistent) |

---

## Tab Management

Tabs are the primary navigation mechanism. Each tab contains one or more panels.

### Dynamic Tabs

- New sessions open in new tabs (`Ctrl+T`)
- Maximum configurable concurrent tabs (default: 10)
- Close tab with `Ctrl+W`
- Switch with `Alt+1` through `Alt+0` or `Tab`/`Shift+Tab`

### Tab Persistence

Tab state persists during the session but not across sessions. Tab content is reconstructed from backend API on reopen. Session history is in the backend, not the TUI.

---

## Keyboard Shortcuts

All shortcuts are configurable via YAML. Defaults follow vim conventions where applicable.

### Global

| Key | Action |
|-----|--------|
| `Ctrl+T` | New tab |
| `Ctrl+W` | Close current tab |
| `Alt+1..0` | Switch to tab 1-10 |
| `Ctrl+Q` | Quit TUI |
| `Ctrl+/` | Command palette |
| `?` | Show help overlay |

### Chat / Input Panels

| Key | Action |
|-----|--------|
| `Ctrl+Enter` | Send message / submit |
| `Up` | Edit last input |
| `Escape` | Cancel current input |
| `Ctrl+L` | Clear display (visual only — history preserved in backend) |

### Navigation

| Key | Action |
|-----|--------|
| `j/k` | Scroll down/up (vim) |
| `g/G` | Top/bottom |
| `/` | Search |
| `Enter` | Expand/select |
| `Escape` | Back/close |

---

## Module Structure

```
modules/tui/
├── __init__.py
├── app.py                      # Main Textual App class
├── config.py                   # TUI configuration loading
├── api_client.py               # REST + WebSocket client
├── screens/
│   ├── __init__.py
│   ├── main.py                 # Main screen with tab container
│   └── login.py                # API key entry (first run)
├── panels/
│   ├── __init__.py
│   └── ...                     # Application-specific panels
├── widgets/
│   ├── __init__.py
│   └── ...                     # Reusable widget components
└── styles/
    └── app.tcss                # Textual CSS stylesheet
```

### Configuration

```yaml
# config/settings/tui.yaml
# =============================================================================
# TUI Configuration
# =============================================================================
# Available options:
#   max_tabs              - Maximum concurrent tabs (integer)
#   default_tabs          - Tabs to open on launch (list of strings)
#   keybindings           - Keyboard shortcut overrides (object)
#     send_message        - Submit input (string, default: ctrl+enter)
#     quit                - Quit TUI (string, default: ctrl+q)
#     new_tab             - Open new tab (string, default: ctrl+t)
#   display               - Display settings (object)
#     timestamp_format    - Timestamp format string (string)
#     show_status_bar     - Show persistent status bar (boolean)
#   connection            - Backend connection settings (object)
#     websocket_reconnect_delay     - Initial reconnect delay in seconds (integer)
#     websocket_max_reconnect_delay - Maximum reconnect delay in seconds (integer)
#     api_timeout                   - REST API timeout in seconds (integer)
# =============================================================================

max_tabs: 10
default_tabs:
  - main
  - dashboard

keybindings:
  send_message: ctrl+enter
  quit: ctrl+q
  new_tab: ctrl+t

display:
  timestamp_format: "%H:%M:%S"
  show_status_bar: true

connection:
  websocket_reconnect_delay: 1
  websocket_max_reconnect_delay: 30
  api_timeout: 30
```

---

## Entry Points

### Terminal

```bash
# Start TUI
python -m modules.tui

# Or via CLI
python cli.py tui
```

### Textual Web (Browser)

```bash
# Serve TUI in browser
textual serve modules.tui.app:TUIApp --port 8080

# Or behind nginx (production)
# upstream tui { server 127.0.0.1:8080; }
```

Textual Web serves the identical application in the browser. No code changes, no separate deployment. The same panels, same keyboard shortcuts, same real-time streaming.

---

## Real-Time Event Handling

### WebSocket Subscriptions

The TUI subscribes to backend events via WebSocket per **21-event-architecture.md**. Define application-specific event handlers for your panels:

```python
class TUIApp(App):
    async def on_websocket_event(self, event: dict) -> None:
        """Route incoming WebSocket events to the appropriate panel."""
        event_type = event.get("type")
        for panel in self.query(BasePanel):
            if event_type in panel.subscribed_events:
                panel.handle_event(event)
```

Events follow the naming convention from 21-event-architecture.md (`{domain}.{entity}.{action}`). Each panel declares which event types it subscribes to.

### Streaming Responses

For operations that stream results (e.g., long-running queries, real-time logs), the panel renders incrementally using Textual's reactive data binding — the widget updates as data arrives, maintaining 60 FPS rendering.

---

## Testing

### Unit Testing

Test panels and widgets in isolation using Textual's pilot testing API:

```python
from textual.testing import AppTest

async def test_panel_renders():
    app = AppTest(TUIApp)
    async with app.run_test() as pilot:
        panel = app.query_one(DashboardPanel)
        assert panel.is_visible

        await pilot.press("ctrl+t")
        await pilot.pause()
        assert len(app.query(Tab)) == 2
```

### Integration Testing

Test TUI against backend:

```python
async def test_sends_with_frontend_id(mock_backend):
    app = AppTest(TUIApp)
    async with app.run_test() as pilot:
        # Trigger an API call
        await pilot.press("enter")
        assert mock_backend.last_request.headers["X-Frontend-ID"] == "tui"
```

### Snapshot Testing

Textual supports SVG snapshots for visual regression testing — render the TUI to SVG and compare against baseline.

---

## Deployment

### Development

```bash
# Run directly
python -m modules.tui

# Run with debug logging
python -m modules.tui --debug
```

### Production (Terminal)

No special deployment — users SSH into the server and run the TUI. Or run locally with API pointing to remote backend.

### Production (Textual Web)

Deploy as a systemd service alongside the backend:

```ini
[Unit]
Description=TUI Web Interface
After=network.target

[Service]
Type=simple
User={app-user}
WorkingDirectory=/opt/{app-name}/current
EnvironmentFile=/opt/{app-name}/.env
ExecStart=/opt/{app-name}/venv/bin/textual serve modules.tui.app:TUIApp --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Nginx reverse proxy for HTTPS:

```nginx
location /tui/ {
    proxy_pass http://127.0.0.1:8080/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

---

## Adoption Checklist

When adopting this module:

- [ ] Install Textual (`pip install textual`)
- [ ] Create `modules/tui/` directory structure
- [ ] Implement main App class with tab container
- [ ] Implement API client (REST + WebSocket)
- [ ] Implement application-specific panels
- [ ] Implement status bar
- [ ] Configure `X-Frontend-ID: tui` on all API calls
- [ ] Add `tui` to log source list in `10-observability.md`
- [ ] Create TUI configuration in `config/settings/tui.yaml`
- [ ] Add CLI entry point (`cli.py tui`)
- [ ] Write panel unit tests with Textual pilot API
- [ ] Test WebSocket reconnection behavior
- [ ] Set up Textual Web for browser access (if needed)

---

## Related Documentation

- [22-frontend-architecture.md](22-frontend-architecture.md) — Thin client principles, CLI (Click), Web (React)
- [21-event-architecture.md](21-event-architecture.md) — WebSocket patterns, event types
- [10-observability.md](10-observability.md) — X-Frontend-ID, log sources
- [01-core-principles.md](01-core-principles.md) — Thin client mandate (P1, P2)
- [46-event-session-architecture.md](46-event-session-architecture.md) — When adopted, the TUI becomes an event subscriber. Agent thinking, tool calls, and response chunks arrive as typed events on the session bus. The TUI renders these in dedicated panels (thinking panel, tool call panel, response panel) rather than polling for updates.
