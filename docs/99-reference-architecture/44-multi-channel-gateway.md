# 44 - Multi-Channel Gateway (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-02-24*

## Changelog

- 1.0.0 (2026-02-24): Initial multi-channel gateway standard — channel adapter interface, session management, real-time push, security enforcement, message routing, daemon mode

---

## Module Status: Optional

This module is **optional**. Adopt when your project:
- Needs to deliver agent interactions through multiple messaging channels (Telegram, Slack, Discord, WebSocket, etc.)
- Requires cross-channel session continuity (same conversation accessible from any channel)
- Needs real-time server-to-client push for agent streaming, approval requests, and cost updates
- Wants centralized security enforcement (rate limiting, DM pairing, input validation) across all channels
- Requires an always-on daemon that maintains persistent connections to messaging platforms

**Dependencies**: This module requires **03-backend-architecture.md** (FastAPI application), **25-telegram-bot-integration.md** (reference channel adapter), and benefits from **40-agentic-architecture.md** + **41-agentic-pydanticai.md** for agent routing.

**Relationship to other modules**: This module sits between external channels and the backend. It does not replace any existing module — it provides the routing layer that connects them:

| Module | Role | Unchanged |
|--------|------|-----------|
| **25-telegram-bot-integration.md** | First channel adapter (Telegram) | ✅ Becomes a channel adapter under this module's interface |
| **27-tui-architecture.md** | TUI client | ✅ Connects via WebSocket defined here |
| **22-frontend-architecture.md** | React web frontend | ✅ Connects via REST + WebSocket defined here |
| **40/41** | Agent orchestration | ✅ Gateway routes messages to the coordinator |
| **27** | External agent interop (MCP/A2A) | ✅ Independent — agents consuming your platform, not messaging channels |

---

## Context

The existing architecture defines several client types — React web frontend (22), CLI (22), Telegram bot (20), TUI (28) — each connecting to the FastAPI backend independently. Each has its own connection model, authentication mechanism, and message format. There is no shared session layer across these clients, no centralized security enforcement point, and no mechanism for the backend to push events to clients that are not actively polling.

This works for a traditional BFF where each client is a distinct application with its own user base. It does not work for a **personal AI assistant** where the user expects to start a conversation on Telegram, continue it on the TUI, and receive a push notification on the web dashboard when a long-running agent task completes. Nor does it work for a multi-channel bot that must enforce the same rate limits, authentication policies, and input validation regardless of which channel a message arrives through.

The multi-channel gateway pattern addresses this by introducing three capabilities:

1. **Channel abstraction**: A standard interface that all channel modules implement, allowing new channels to be added without modifying the core routing logic
2. **Session management**: Cross-channel sessions that maintain conversation context regardless of which channel the user is currently using
3. **Real-time push**: A WebSocket connection layer that enables the backend to push events (agent responses, approval requests, cost updates) to any connected client

The gateway is not a separate process. It is a set of components within the existing FastAPI application — a WebSocket endpoint, a session manager, a channel adapter registry, and security middleware. For deployments that need an always-on daemon (maintaining persistent connections to WhatsApp, Signal, etc.), a separate long-running process is defined that connects to the FastAPI backend via the same API.

---

## Architecture

```
                    Inbound Channels
                    ─────────────────
    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ Telegram │  │  Slack   │  │ Discord  │  │ WebSocket│
    │ Webhook  │  │  Bolt    │  │ Gateway  │  │ Clients  │
    └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
    ┌────────────────────────────────────────────────────────┐
    │              Channel Adapter Registry                   │
    │                                                        │
    │  Each adapter implements ChannelAdapter interface:      │
    │  - receive_message() → ChannelMessage                  │
    │  - deliver_response() ← AgentResponse                  │
    │  - format_for_channel() (chunking, markdown, media)    │
    └──────────────────────┬─────────────────────────────────┘
                           │
                           ▼
    ┌────────────────────────────────────────────────────────┐
    │              Gateway Security Layer                     │
    │                                                        │
    │  - DM pairing (default-deny for unknown senders)       │
    │  - Rate limiting (per-user, per-channel)               │
    │  - Input validation (max length, injection patterns)   │
    │  - Allowlist enforcement                               │
    └──────────────────────┬─────────────────────────────────┘
                           │
                           ▼
    ┌────────────────────────────────────────────────────────┐
    │              Session Manager                           │
    │                                                        │
    │  - Session lookup/creation by (user_id, channel)       │
    │  - Cross-channel session binding                       │
    │  - Session type enforcement (direct/group)             │
    │  - Tool access level (full/sandbox/readonly)           │
    └──────────────────────┬─────────────────────────────────┘
                           │
                           ▼
    ┌────────────────────────────────────────────────────────┐
    │              Message Router                             │
    │                                                        │
    │  - Chat commands intercepted (/status, /new, /usage)   │
    │  - Agent requests → Coordinator (doc 41)               │
    │  - Responses routed back through originating channel   │
    │  - Cross-channel push for connected WebSocket clients  │
    └──────────────────────┬─────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
    ┌──────────────┐ ┌──────────┐ ┌──────────────┐
    │ Coordinator  │ │  REST    │ │  Background  │
    │ (doc 41)     │ │  API     │ │  Tasks       │
    │ handle()     │ │          │ │  (Taskiq)    │
    └──────────────┘ └──────────┘ └──────────────┘
```

### Data Flow

**Inbound** (user sends message through any channel):
1. Channel adapter receives message in channel-native format
2. Adapter translates to `ChannelMessage` (standard internal format)
3. Security layer validates: allowlist, rate limit, input validation
4. Session manager resolves or creates session
5. Router checks for chat commands (intercept) or forwards to coordinator
6. Coordinator processes via agent runtime (doc 41)
7. Response returned to router

**Outbound** (agent response delivered to user):
1. Router receives `AgentResponse` from coordinator
2. Router resolves which channel(s) to deliver through
3. Channel adapter formats for target channel (chunking, markdown, media)
4. Adapter delivers through channel-native API
5. If WebSocket clients are connected, push event simultaneously

**Push** (backend-initiated event to connected clients):
1. Backend publishes event (task complete, approval needed, cost warning)
2. WebSocket manager checks which clients are subscribed to this session
3. Event pushed to all connected clients for that session
4. Clients may be on different channels — each receives the event in their native format

---

## Channel Adapter Interface

Every channel module implements a standard interface. This is the contract that allows new channels to be added without modifying routing, security, or session logic.

### ChannelMessage (Inbound)

```python
from dataclasses import dataclass, field
from modules.backend.core.utils import utc_now


@dataclass
class ChannelMessage:
    """Standard internal message format. All channel adapters produce this."""

    channel: str
    user_id: str
    text: str
    session_key: str
    message_id: str | None = None
    group_id: str | None = None
    is_group: bool = False
    reply_to_message_id: str | None = None
    media: list[dict] | None = None
    raw_event: dict | None = None
    received_at: str = field(default_factory=lambda: utc_now().isoformat())
```

### AgentResponse (Outbound)

```python
@dataclass
class AgentResponse:
    """Standard response format. Router delivers this through channel adapters."""

    text: str
    session_key: str
    channel: str
    reply_to_message_id: str | None = None
    media: list[dict] | None = None
    cost_usd: float | None = None
    token_input: int | None = None
    token_output: int | None = None
    duration_ms: int | None = None
    agent_name: str | None = None
```

### ChannelAdapter Base Class

```python
from abc import ABC, abstractmethod


class ChannelAdapter(ABC):
    """
    Base class for all channel adapters.

    Each messaging channel implements this interface. The gateway
    interacts with channels exclusively through this contract.
    """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Unique channel identifier (e.g., 'telegram', 'slack', 'discord')."""
        ...

    @abstractmethod
    async def deliver_response(self, response: AgentResponse) -> bool:
        """
        Deliver an agent response through this channel.

        Handles channel-specific formatting (chunking, markdown
        conversion, media attachments). Returns True if delivered.
        """
        ...

    @abstractmethod
    def format_text(self, text: str) -> str:
        """
        Format text for this channel's constraints.

        Handles markdown dialect differences, character limits,
        and other channel-specific formatting requirements.
        """
        ...

    @property
    @abstractmethod
    def max_message_length(self) -> int:
        """Maximum message length for this channel."""
        ...

    async def chunk_message(self, text: str) -> list[str]:
        """
        Split a long message into channel-appropriate chunks.

        Default implementation splits on paragraph boundaries
        within max_message_length. Override for channel-specific
        chunking logic (e.g., Telegram's 4096 limit, Discord's 2000).
        """
        if len(text) <= self.max_message_length:
            return [text]

        chunks = []
        remaining = text
        while remaining:
            if len(remaining) <= self.max_message_length:
                chunks.append(remaining)
                break

            split_at = remaining[:self.max_message_length].rfind("\n\n")
            if split_at == -1:
                split_at = remaining[:self.max_message_length].rfind("\n")
            if split_at == -1:
                split_at = self.max_message_length

            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip()

        return chunks
```

### Channel-Specific Constraints

| Channel | Max Message Length | Markdown | Media | Webhooks | Group Support |
|---------|------------------|----------|-------|----------|---------------|
| Telegram | 4096 chars | HTML subset or MarkdownV2 | Photos, documents, audio, video | Webhook with secret | Yes (mention gating) |
| Slack | 40,000 chars (Block Kit) | mrkdwn (Slack-specific) | Files via upload API | Events API or Socket Mode | Yes (app mentions) |
| Discord | 2000 chars | Standard Markdown | Attachments, embeds | Gateway (WebSocket) | Yes (role-based) |
| WebSocket | Unlimited (practical: 1MB) | Standard Markdown | Base64 or URLs | N/A (bidirectional) | N/A |
| WhatsApp Business | 4096 chars | Limited formatting | Images, documents | Webhook | Yes |

Adapters handle these differences internally. The router and session manager work exclusively with `ChannelMessage` and `AgentResponse` — they never see channel-native formats.

---

## Session Management

### Session Model

A session represents a conversation context. It is identified by a composite key and carries metadata that controls agent behavior.

```python
@dataclass
class GatewaySession:
    """
    Gateway session binding a user-channel pair to a conversation.

    Sessions persist across messages. A user may have multiple sessions
    (one per group, one DM). Cross-channel binding allows the same
    conversation to be accessed from different channels.
    """

    session_id: str
    user_id: str
    channel: str
    session_type: str
    group_id: str | None = None
    conversation_id: str | None = None
    tool_access_level: str = "sandbox"
    activation_mode: str = "always"
    is_active: bool = True
    created_at: str = ""
    last_active_at: str = ""
```

### Session Types

| Type | Description | Tool Access Default | Created When |
|------|-------------|-------------------|--------------|
| `direct` | 1:1 DM between user and assistant | `sandbox` | User sends first DM |
| `group` | Group/channel conversation | `readonly` | Bot added to group or first group mention |

### Tool Access Levels

| Level | Description | Use Case |
|-------|-------------|----------|
| `full` | Agent can use all tools including file system, subprocess | Explicitly elevated by admin for trusted sessions |
| `sandbox` | Agent can use domain tools (database, API calls) but not system tools | Default for DM sessions |
| `readonly` | Agent can only use read-only tools (search, query) | Default for group sessions |

Tool access is configured per session in `config/settings/gateway.yaml` and enforced by the session manager before the coordinator receives the request. The coordinator's `CoordinatorRequest` (doc 41) carries the session's `tool_access_level`, and the tool registry filters available tools accordingly.

### Cross-Channel Session Binding

A user may access the same conversation from different channels. The session manager maintains bindings:

```
User "alice" on Telegram DM  →  session_id: "sess-abc-123"
User "alice" on WebSocket     →  session_id: "sess-abc-123"  (same session)
User "alice" in Slack group   →  session_id: "sess-def-456"  (different session)
```

Binding is by `user_id` — the session manager maps each channel's native user identifier to an internal `user_id`. For channels where the user cannot be identified across platforms (no shared email or phone), cross-channel binding requires explicit pairing (the user links accounts via a command).

### Session Storage

| Store | Data | TTL |
|-------|------|-----|
| Redis | Active session state, connection tracking, ephemeral working data | Configurable per `gateway.yaml` |
| PostgreSQL | Session history, conversation records, audit trail | Permanent (with archival policy) |

Active sessions live in Redis for fast lookup. When a session becomes inactive (no messages for the configured TTL), it is archived to PostgreSQL. Reactivation loads from PostgreSQL back into Redis.

---

## Real-Time Push via WebSocket

### WebSocket Endpoint

The FastAPI application exposes a WebSocket endpoint for real-time bidirectional communication. This serves the TUI (doc 45), the React frontend (22), and any other client that needs server-pushed events.

```python
from fastapi import WebSocket, WebSocketDisconnect
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for real-time event streaming.

    Clients connect with a session_id and receive events for that session.
    Authentication is required — the client must provide a valid token
    in the initial connection request.
    """
    await websocket.accept()

    connection_manager = get_connection_manager()
    connection_id = await connection_manager.connect(websocket, session_id)

    try:
        while True:
            data = await websocket.receive_json()
            await handle_websocket_message(data, session_id, connection_id)
    except WebSocketDisconnect:
        await connection_manager.disconnect(connection_id)
        logger.debug("WebSocket disconnected", extra={"session_id": session_id})
```

### Connection Manager

The connection manager tracks active WebSocket connections and routes events to subscribed clients.

```python
class ConnectionManager:
    """
    Manages WebSocket connections and event routing.

    Tracks which connections are subscribed to which sessions.
    Routes events from the backend to connected clients.
    """

    async def connect(self, websocket: WebSocket, session_id: str) -> str:
        """Register a new connection for a session. Returns connection_id."""
        ...

    async def disconnect(self, connection_id: str) -> None:
        """Remove a connection."""
        ...

    async def push_event(self, session_id: str, event: dict) -> int:
        """
        Push an event to all connections subscribed to a session.

        Returns the number of clients that received the event.
        """
        ...

    async def broadcast(self, event: dict) -> int:
        """Push an event to all connected clients (system-wide alerts)."""
        ...
```

Connection state is stored in Redis, enabling multiple FastAPI worker processes to share connection tracking. Each worker manages its own WebSocket connections, but Redis provides the shared registry for cross-worker event routing.

### Event Types

Events pushed through WebSocket follow the event schema from **21-event-architecture.md** with gateway-specific additions:

| Event | Payload | When |
|-------|---------|------|
| `agent.response.chunk` | `{text, agent_name, is_final}` | Agent streams response tokens |
| `agent.response.complete` | `{text, cost_usd, tokens, duration_ms, agent_name}` | Agent finishes response |
| `agent.reasoning.step` | `{step_number, action, detail, cost}` | Agent reasoning step (for TUI/debug) |
| `agent.tool.call` | `{tool_name, parameters}` | Agent invokes a tool |
| `agent.tool.result` | `{tool_name, result, duration_ms}` | Tool returns result |
| `approval.required` | `{approval_id, agent_name, action, context}` | Human approval needed |
| `approval.resolved` | `{approval_id, decision, resolved_by}` | Approval decision made |
| `plan.step.completed` | `{plan_id, step, status, cost}` | Plan step finished |
| `plan.completed` | `{plan_id, total_cost, total_duration_ms}` | Entire plan finished |
| `cost.warning` | `{current, limit, scope}` | Cost approaching budget |
| `cost.exceeded` | `{current, limit, scope}` | Budget exceeded, execution stopped |
| `session.updated` | `{session_id, changes}` | Session metadata changed |

### WebSocket Authentication

WebSocket connections must be authenticated before receiving events. Authentication happens during the connection handshake:

1. Client includes a token in the WebSocket URL query parameter or first message
2. Server validates the token using the existing JWT infrastructure (05-authentication.md)
3. If invalid, server closes the connection with code 4001
4. If valid, server registers the connection and begins streaming events

Tokens must include an `aud` (audience) claim matching the configured gateway audience in `security.yaml`.

---

## Gateway Security Layer

Security enforcement happens once, at the gateway level, before messages reach the session manager or router. Every channel adapter's inbound messages pass through the same security pipeline. This eliminates the need to duplicate security logic across channel adapters.

### Default-Deny Policy

The gateway's default policy is **deny**. Unknown senders on any channel are rejected unless explicitly configured otherwise. This is the inverse of OpenClaw's early "open by default" approach and prevents the class of vulnerabilities where missing configuration silently degrades to open access.

| Policy | Behavior | Configuration |
|--------|----------|---------------|
| `deny` | Unknown senders receive no response. Message is logged and dropped. | Default. No configuration needed. |
| `pairing` | Unknown senders receive a one-time pairing code. Admin approves via API/CLI. Once paired, the sender is added to the allowlist. | Set `default_policy: "pairing"` in `gateway.yaml`. |
| `allowlist` | Only senders in the configured allowlist can interact. All others are denied. | Set `default_policy: "allowlist"` and populate `allowlists` in `gateway.yaml`. |

The `deny` default means that **deploying the application with an empty allowlist results in a bot that responds to nobody** — which is the correct security posture for a system that has not been configured yet.

### DM Pairing Protocol

For channels where users cannot be pre-configured (public-facing bots), the pairing protocol provides controlled onboarding:

1. Unknown user sends a message through any channel
2. Gateway generates a 6-character alphanumeric code with a configurable TTL
3. Gateway responds to the user: "Send this code to the admin to get access: `ABC123`"
4. Admin approves via CLI: `python cli.py --service approve-pairing --code ABC123`
5. User's channel-specific ID is added to the persistent allowlist
6. Subsequent messages from this user are processed normally

Pairing codes are stored in Redis with TTL. Expired codes are automatically invalidated.

### Rate Limiting

Rate limits are enforced per user, per channel, at the gateway level. Configuration comes from `security.yaml`:

```yaml
rate_limiting:
  telegram:
    messages_per_minute: 30
    messages_per_hour: 500
  slack:
    messages_per_minute: 30
    messages_per_hour: 500
  discord:
    messages_per_minute: 30
    messages_per_hour: 500
  websocket:
    messages_per_minute: 60
    messages_per_hour: 1000
```

Rate limiting uses Redis for distributed state. When a limit is exceeded, the gateway responds with a channel-appropriate message indicating the cooldown period, and the message is not forwarded to the router.

### Input Validation

Before any message reaches the agent coordinator, the gateway validates:

1. **Message length**: Enforced per `gateway.yaml` `max_input_length`. Messages exceeding the limit are rejected with a user-facing error.
2. **Injection patterns**: Regex patterns from `security.yaml` `guardrails.injection_patterns` are checked. Matches are logged as security events and the message is rejected.
3. **Media validation**: If media is attached, validate file type and size against configured limits.

These checks run after rate limiting and before session resolution — a rejected message does not consume a rate limit token.

### Startup Validation

The gateway validates security invariants at startup. If any check fails, the application refuses to start:

| Check | Condition | Failure Behavior |
|-------|-----------|-----------------|
| Webhook secrets | If a channel with webhooks is enabled, its secret must be non-empty | Startup failure with specific error message |
| JWT secret strength | `JWT_SECRET` must be at least 32 characters | Startup failure |
| Production safety | In `production` environment: `debug` must be false, `api_detailed_errors` must be false | Startup failure |
| Allowlist sanity | If any channel is enabled with `default_policy: "allowlist"`, the allowlist must be non-empty | Startup failure |

These checks prevent the "missing configuration silently degrades to open access" pattern that caused OpenClaw's security incidents.

---

## Message Router

The router sits between the security layer and the agent coordinator. It intercepts chat commands, forwards agent requests, and routes responses back through the appropriate channel.

### Chat Commands

Chat commands are channel-agnostic directives that the router intercepts before forwarding to the agent. They work identically across all channels.

| Command | Action | Scope |
|---------|--------|-------|
| `/status` | Show session status: model, tokens used, cost | Session |
| `/new` | Reset the current session (clear context) | Session |
| `/usage off\|tokens\|full` | Control cost footer on responses | Session |
| `/help` | Show available commands | Global |
| `/cancel` | Cancel the currently running agent task (kill switch) | Session |

Commands are recognized by the `/` prefix. The router strips the command and dispatches to the appropriate handler. Commands never reach the agent coordinator.

### Agent Request Routing

Non-command messages are forwarded to the agent coordinator:

1. Router constructs a `CoordinatorRequest` (doc 41) from the `ChannelMessage`
2. `session_id`, `user_id`, `entry_point`, and `tool_access_level` are populated from the session
3. Router calls `handle(request)` (doc 41)
4. Response is wrapped in an `AgentResponse` and delivered through the channel adapter

### Response Delivery

The router delivers responses through two paths simultaneously:

1. **Origin channel**: The response is delivered through the same channel adapter that received the inbound message
2. **Connected WebSocket clients**: If the user has active WebSocket connections (TUI, web frontend), the response is pushed as an event

This ensures the user sees the response regardless of which channel they're currently looking at.

### Cost Footer

When `/usage` is set to `tokens` or `full`, the router appends cost metadata to every response before delivery:

- `tokens`: `📊 2.1K tokens`
- `full`: `📊 2.1K tokens · $0.03 · code_reviewer · 4.2s`

The footer format is configured in `gateway.yaml`. Channel adapters handle formatting (e.g., Telegram uses a dim/italic style, Discord uses a code block).

---

## Module Structure

```
modules/
├── gateway/
│   ├── __init__.py
│   ├── adapters/
│   │   ├── __init__.py              # ChannelAdapter base class, ChannelMessage, AgentResponse
│   │   ├── telegram.py              # Telegram adapter (wraps modules/telegram/)
│   │   ├── slack.py                 # Slack adapter (slack-bolt)
│   │   ├── discord.py               # Discord adapter (discord.py)
│   │   └── websocket.py             # WebSocket adapter (built-in)
│   ├── security/
│   │   ├── __init__.py
│   │   ├── pairing.py               # DM pairing protocol
│   │   ├── rate_limiter.py          # Per-user, per-channel rate limiting
│   │   ├── input_validator.py       # Message length, injection patterns
│   │   └── startup_checks.py        # Security invariant validation at startup
│   ├── sessions/
│   │   ├── __init__.py
│   │   ├── manager.py               # Session lifecycle, cross-channel binding
│   │   ├── models.py                # GatewaySession dataclass
│   │   └── storage.py               # Redis + PostgreSQL session storage
│   ├── router/
│   │   ├── __init__.py
│   │   ├── router.py                # Message routing, chat command dispatch
│   │   ├── commands.py              # Chat command handlers (/status, /new, /usage, etc.)
│   │   └── cost_footer.py           # Cost metadata formatting
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── endpoint.py              # FastAPI WebSocket endpoint
│   │   ├── connection_manager.py    # Connection tracking and event routing
│   │   └── auth.py                  # WebSocket authentication
│   └── registry.py                  # Channel adapter registry
├── telegram/
│   └── ...                          # Existing Telegram module (unchanged)
├── backend/
│   └── ...                          # Existing backend (unchanged)
config/
└── settings/
    └── gateway.yaml                 # Gateway configuration
```

### Relationship to Existing Telegram Module

The existing `modules/telegram/` module is not replaced. The Telegram channel adapter (`modules/gateway/adapters/telegram.py`) wraps it — translating between the gateway's `ChannelMessage`/`AgentResponse` format and aiogram's native types. The Telegram module retains its handlers, keyboards, FSM states, and middlewares. The gateway adds the session management, cross-channel routing, and security enforcement layer on top.

---

## Configuration

```yaml
# config/settings/gateway.yaml
# =============================================================================
# Multi-Channel Gateway Configuration
# =============================================================================
# Available options:
#   enabled            - Enable the gateway (boolean)
#   default_policy     - Default security policy for unknown senders
#                        (string: deny|pairing|allowlist)
#   pairing            - DM pairing settings (object)
#     code_length      - Pairing code length (integer)
#     code_ttl_seconds - Pairing code expiration (integer)
#   channels           - Per-channel configuration (object)
#     {channel_name}   - Channel-specific settings (object)
#       enabled        - Enable this channel (boolean)
#       allowlist      - User IDs allowed to interact (list of strings)
#       activation_mode - Group behavior (string: always|mention)
#       tool_access_level - Default tool access (string: full|sandbox|readonly)
#   sessions           - Session management settings (object)
#     ttl_seconds      - Inactive session TTL in Redis (integer)
#     max_per_user     - Maximum concurrent sessions per user (integer)
#     max_history      - Maximum messages in session context (integer)
#   websocket          - WebSocket settings (object)
#     enabled          - Enable WebSocket endpoint (boolean)
#     path             - WebSocket URL path (string)
#     heartbeat_seconds - Heartbeat interval (integer)
#     max_connections  - Maximum concurrent connections (integer)
#   router             - Message routing settings (object)
#     cost_footer      - Cost footer mode (string: off|tokens|full)
#     max_input_length - Maximum inbound message length (integer)
#   commands           - Chat command settings (object)
#     prefix           - Command prefix character (string)
#     enabled          - List of enabled commands (list of strings)
# =============================================================================

enabled: true

default_policy: "deny"

pairing:
  code_length: 6
  code_ttl_seconds: 300

channels:
  telegram:
    enabled: false
    allowlist: []
    activation_mode: "mention"
    tool_access_level: "sandbox"
  slack:
    enabled: false
    allowlist: []
    activation_mode: "mention"
    tool_access_level: "sandbox"
  discord:
    enabled: false
    allowlist: []
    activation_mode: "mention"
    tool_access_level: "readonly"

sessions:
  ttl_seconds: 3600
  max_per_user: 10
  max_history: 50

websocket:
  enabled: true
  path: "/ws"
  heartbeat_seconds: 30
  max_connections: 100

router:
  cost_footer: "off"
  max_input_length: 32000

commands:
  prefix: "/"
  enabled:
    - status
    - new
    - usage
    - help
    - cancel
```

All channels are **disabled by default**. Each channel must be explicitly enabled in configuration. This ensures that deploying the application does not accidentally expose any channel without deliberate configuration.

---

## Adding a New Channel

Adding a channel requires three steps:

**1. Implement the channel adapter**

Create `modules/gateway/adapters/{channel}.py` implementing `ChannelAdapter`:

```python
from modules.gateway.adapters import ChannelAdapter, ChannelMessage, AgentResponse


class SlackAdapter(ChannelAdapter):
    """Slack channel adapter using slack-bolt."""

    @property
    def channel_name(self) -> str:
        return "slack"

    @property
    def max_message_length(self) -> int:
        return 40000

    async def deliver_response(self, response: AgentResponse) -> bool:
        formatted = self.format_text(response.text)
        chunks = await self.chunk_message(formatted)
        for chunk in chunks:
            await self._slack_client.chat_postMessage(
                channel=response.session_key,
                text=chunk,
            )
        return True

    def format_text(self, text: str) -> str:
        return _markdown_to_mrkdwn(text)
```

**2. Add channel configuration**

Add the channel to `gateway.yaml` under `channels:` with `enabled: false` (secure default).

**3. Register the adapter**

Add the adapter to the channel registry in `modules/gateway/registry.py`. The gateway discovers registered adapters at startup and enables those with `enabled: true` in configuration.

No changes to the router, session manager, or security layer are needed. The new channel inherits all gateway capabilities automatically: rate limiting, DM pairing, session management, cross-channel push, and cost footers.

---

## Daemon Mode

For channels that require persistent connections (WhatsApp via Baileys, Signal via signal-cli), the FastAPI request-response model is insufficient — these channels need a long-running process that maintains the connection.

### Architecture

```
┌──────────────────────────────────────────┐
│  Gateway Daemon (long-running process)    │
│                                          │
│  Maintains persistent connections to:    │
│  - WhatsApp (Baileys WebSocket)          │
│  - Signal (signal-cli subprocess)        │
│                                          │
│  Translates inbound messages to HTTP     │
│  calls to the FastAPI backend.           │
│  Receives responses via webhook/polling. │
└──────────────────┬───────────────────────┘
                   │
                   │  HTTP (REST API)
                   │
                   ▼
┌──────────────────────────────────────────┐
│  FastAPI Application                      │
│  (same backend, same security, same API) │
└──────────────────────────────────────────┘
```

The daemon is a separate Python process that:
1. Maintains persistent connections to channels that require them
2. Receives inbound messages from these channels
3. Translates them to `ChannelMessage` format
4. Forwards to the FastAPI backend via HTTP (the same API the TUI and web frontend use)
5. Receives responses and delivers them back through the channel

The daemon is optional — channels with webhook support (Telegram, Slack) do not need it. It is only required for channels that use persistent connections.

### Entry Point

```bash
python cli.py --service gateway-daemon --verbose
```

The daemon uses the same configuration (`gateway.yaml`), the same security rules, and the same session model as the embedded gateway. It is a deployment option, not an architectural change.

---

## Testing

### Channel Adapter Testing

Test adapters in isolation by mocking the channel-native client:

```python
import pytest
from unittest.mock import AsyncMock
from modules.gateway.adapters.telegram import TelegramAdapter
from modules.gateway.adapters import AgentResponse


@pytest.fixture
def telegram_adapter(mock_bot):
    return TelegramAdapter(bot=mock_bot)


@pytest.mark.asyncio
async def test_long_message_chunked(telegram_adapter):
    response = AgentResponse(
        text="A" * 5000,
        session_key="chat_123",
        channel="telegram",
    )
    result = await telegram_adapter.deliver_response(response)
    assert result is True
    assert telegram_adapter._bot.send_message.call_count == 2
```

### Security Layer Testing

Test security enforcement with both allowed and denied messages:

```python
@pytest.mark.asyncio
async def test_unknown_sender_denied(gateway_security):
    message = ChannelMessage(
        channel="telegram",
        user_id="unknown_user",
        text="Hello",
        session_key="dm_unknown",
    )
    result = await gateway_security.validate(message)
    assert result.denied is True
    assert result.reason == "sender_not_in_allowlist"


@pytest.mark.asyncio
async def test_rate_limit_enforced(gateway_security):
    message = ChannelMessage(
        channel="telegram",
        user_id="allowed_user",
        text="Hello",
        session_key="dm_allowed",
    )
    for _ in range(31):
        await gateway_security.validate(message)
    result = await gateway_security.validate(message)
    assert result.denied is True
    assert result.reason == "rate_limit_exceeded"
```

### Session Manager Testing

```python
@pytest.mark.asyncio
async def test_cross_channel_session_binding(session_manager):
    session1 = await session_manager.resolve("alice", "telegram")
    session2 = await session_manager.resolve("alice", "websocket")
    assert session1.session_id == session2.session_id


@pytest.mark.asyncio
async def test_group_session_isolation(session_manager):
    dm_session = await session_manager.resolve("alice", "telegram")
    group_session = await session_manager.resolve(
        "alice", "telegram", group_id="group_123"
    )
    assert dm_session.session_id != group_session.session_id
    assert group_session.session_type == "group"
    assert group_session.tool_access_level == "readonly"
```

### WebSocket Testing

```python
from fastapi.testclient import TestClient


def test_websocket_requires_auth(client: TestClient):
    with client.websocket_connect("/ws?session_id=test") as ws:
        ws.send_json({"type": "auth", "token": "invalid"})
        response = ws.receive_json()
        assert response["type"] == "error"
        assert response["code"] == 4001
```

### Integration Testing

Test the full message flow from inbound to agent response:

```python
@pytest.mark.asyncio
async def test_telegram_message_to_agent_response(
    gateway, mock_coordinator, telegram_adapter
):
    message = ChannelMessage(
        channel="telegram",
        user_id="allowed_user",
        text="Review my code",
        session_key="dm_allowed",
    )

    mock_coordinator.handle.return_value = CoordinatorResponse(
        output="Found 2 issues...",
    )

    await gateway.process_inbound(message)

    mock_coordinator.handle.assert_awaited_once()
    telegram_adapter.deliver_response.assert_awaited_once()
```

---

## Adoption Checklist

### Phase 1: WebSocket + Session Foundation

- [ ] Create `modules/gateway/` directory structure
- [ ] Implement `ChannelAdapter` base class and data models (`ChannelMessage`, `AgentResponse`)
- [ ] Implement session manager with Redis storage
- [ ] Implement WebSocket endpoint on FastAPI
- [ ] Implement connection manager with Redis-backed connection tracking
- [ ] Implement WebSocket authentication
- [ ] Add `gateway.yaml` to `config/settings/`
- [ ] Add `gateway` to feature flags in `features.yaml`
- [ ] Write session manager tests
- [ ] Write WebSocket connection tests

### Phase 2: Security Layer

- [ ] Implement startup security validation
- [ ] Implement default-deny policy enforcement
- [ ] Implement DM pairing protocol with Redis-backed code storage
- [ ] Implement gateway-level rate limiting (Redis-backed)
- [ ] Implement input validation (length, injection patterns)
- [ ] Write security layer tests (deny, pairing, rate limit, injection)
- [ ] Add `--action approve-pairing` to CLI

### Phase 3: Telegram Adapter

- [ ] Implement Telegram channel adapter wrapping existing `modules/telegram/`
- [ ] Register adapter in channel registry
- [ ] Wire adapter through gateway security and session layers
- [ ] Mount Telegram webhook through gateway (instead of directly on FastAPI)
- [ ] Write adapter tests (chunking, formatting, delivery)
- [ ] Test end-to-end: Telegram message → gateway → coordinator → response

### Phase 4: Router + Chat Commands

- [ ] Implement message router with chat command interception
- [ ] Implement chat commands (`/status`, `/new`, `/usage`, `/help`, `/cancel`)
- [ ] Implement cost footer formatting
- [ ] Wire router between security layer and coordinator
- [ ] Write router tests (command dispatch, agent forwarding, cost footer)

### Phase 5: Additional Channels

- [ ] Implement Slack adapter (slack-bolt)
- [ ] Implement Discord adapter (discord.py)
- [ ] Add channel configurations to `gateway.yaml`
- [ ] Write adapter tests for each new channel
- [ ] Test cross-channel session continuity

### Phase 6: Daemon Mode (Optional)

- [ ] Implement gateway daemon process for persistent-connection channels
- [ ] Add `--action gateway-daemon` to CLI
- [ ] Create systemd/launchd service configuration
- [ ] Write daemon health check and reconnection tests

---

## Event-Driven Channel Adapters (Doc 46)

When the project adopts `46-event-session-architecture.md`, channel adapters become event subscribers rather than direct service callers.

### Architectural Shift

| Concern | Without Doc 46 | With Doc 46 |
|---------|---------------|-------------|
| Session state | Per-channel tracking | Centralized `SessionService` — channels bind to sessions via `session.bind_channel()` |
| Message handling | Channel calls service layer directly | Channel publishes `UserMessageEvent` → coordinator handles → channel subscribes to response events |
| Response delivery | Service returns response, adapter formats it | Adapter subscribes to `session:{id}` event channel, renders events in channel-native format |
| Streaming | Channel-specific streaming implementation | Universal — coordinator yields `AsyncIterator[Event]`, each adapter renders events differently |
| Multi-channel | Separate session per channel | Single session, multiple channel bindings — user can start in Telegram, continue in TUI |

### Channel Adapter Pattern (Event-Driven)

Each channel adapter performs three operations:

1. **Ingest**: Convert channel-native input (Telegram message, WebSocket frame, TUI keypress) into a `UserMessageEvent` and publish to the event bus.
2. **Subscribe**: Subscribe to `session:{session_id}` channel on Redis pub/sub.
3. **Render**: Convert session events into channel-native output.

```python
# Conceptual pattern — each channel implements this differently
class ChannelAdapter:
    async def on_user_input(self, channel_input) -> None:
        session = await self.resolve_session(channel_input)
        event = UserMessageEvent(session_id=session.id, content=channel_input.text)
        await event_bus.publish(event)

    async def subscribe(self, session_id: str) -> None:
        async for event in event_bus.subscribe(f"session:{session_id}"):
            await self.render(event)

    async def render(self, event: SessionEvent) -> None:
        # Channel-specific rendering
        raise NotImplementedError
```

### Channel-Specific Rendering

| Event Type | REST/SSE | Telegram | TUI | WebSocket |
|-----------|----------|----------|-----|-----------|
| `AgentThinkingEvent` | SSE `event: thinking` | Edit message with "⏳ Thinking..." | Update thinking panel | JSON frame `{type: "thinking"}` |
| `AgentResponseChunkEvent` | SSE `event: chunk` | Buffer chunks, edit message every 500ms | Append to response panel | JSON frame `{type: "chunk", content: "..."}` |
| `AgentToolCallEvent` | SSE `event: tool_call` | Inline "🔧 Searching..." | Tool call panel | JSON frame `{type: "tool_call"}` |
| `ApprovalRequestedEvent` | SSE `event: approval` + poll endpoint | Inline keyboard buttons | Modal dialog | JSON frame `{type: "approval"}` |

### Session-Channel Binding

Sessions support multiple channel bindings. A user can start a conversation in Telegram and continue it in the TUI — same session, same history, same plan state.

```python
await session_service.bind_channel(session_id, channel_type="telegram", channel_id="chat_12345")
await session_service.bind_channel(session_id, channel_type="tui", channel_id="tui_session_abc")
```

The session service maintains a `session_channels` table mapping session IDs to channel bindings.

### Migration Path

Existing channel adapters can be migrated incrementally:
1. Add event bus subscription alongside existing direct service calls
2. Route new features through events, keep existing features on direct calls
3. Once all features use events, remove direct service calls

The existing per-channel session tracking in doc 44 remains valid for projects that do not adopt doc 46.

See `46-event-session-architecture.md`, Section 3 (Streaming Coordinator — Channel Adapters) for the complete adapter implementations.

---

## Related Documentation

- [03-backend-architecture.md](03-backend-architecture.md) — FastAPI application where WebSocket endpoint is mounted
- [25-telegram-bot-integration.md](25-telegram-bot-integration.md) — Telegram module (first channel adapter)
- [40-agentic-architecture.md](40-agentic-architecture.md) — Agent orchestration, session concepts, cost tracking
- [41-agentic-pydanticai.md](41-agentic-pydanticai.md) — Coordinator `handle()`, entry points, streaming
- [42-agent-first-infrastructure.md](42-agent-first-infrastructure.md) — MCP/A2A (external agent interop, independent of messaging channels)
- [27-tui-architecture.md](27-tui-architecture.md) — TUI client (connects via WebSocket defined here)
- [22-frontend-architecture.md](22-frontend-architecture.md) — React web frontend, CLI
- [21-event-architecture.md](21-event-architecture.md) — Event types, WebSocket patterns
- [05-authentication.md](05-authentication.md) — JWT authentication (extended for WebSocket)
- [10-observability.md](10-observability.md) — Source-based logging, X-Frontend-ID
- [98-research/07-Personal AI assistant architecture](../98-research/07-Personal%20AI%20assistant%20architecture-%20lessons%20from%20OpenClaw%20for%20agent-first%20platforms.md) — Analysis that motivated this module
- [46-event-session-architecture.md](46-event-session-architecture.md) — Channels as event subscribers, session-channel binding, unified session state
