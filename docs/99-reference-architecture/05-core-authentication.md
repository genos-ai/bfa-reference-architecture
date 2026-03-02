# 05 - Authentication and Authorization

*Version: 1.1.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.1.0 (2026-02-11): Refocused on authentication/authorization; security standards moved to 06-security-standards.md, data protection to 07-data-protection.md
- 1.0.0 (2025-01-27): Initial generic authentication and security standard

---

## Context

Authentication and authorization are the most security-critical parts of any application. Getting them wrong means data breaches, unauthorized access, or privilege escalation. This document defines the authentication methods, token lifecycle, authorization model, and rate limiting standards that every project must implement.

The architecture supports three authentication methods because different clients have different needs: API keys for programmatic access (CLI, service-to-service, integrations), JWT tokens for web sessions (short-lived access + long-lived refresh), and session cookies as an alternative for traditional web flows. API keys are the primary method because they are simpler, stateless, and work across all client types.

The key design decision is that authorization checks happen in the service layer, not the API layer. This ensures that business rules about who can access what are enforced regardless of how the service is called — whether from an HTTP endpoint, a background task, or another module's internal API. Security standards (06) and data protection (07) complement this document with deeper technical controls and privacy requirements respectively.

---

## Authentication Methods

### API Keys

Primary authentication for all programmatic access.

Use cases:
- CLI applications
- Service-to-service communication
- Third-party integrations

Key format: `prefix_randomstring`
- Prefix identifies key type (e.g., `app_` for application)
- Random string: 32+ characters, cryptographically random

Key storage:
- Database stores hashed key (bcrypt)
- Full key shown only at creation time
- Keys can be named for identification

Key lifecycle:
- User creates key via web interface or API
- Keys have optional expiration
- Keys can be revoked immediately
- Revoked keys rejected on next use

### JWT Tokens

Used for web session management.

Token types:
- Access token: Short-lived (30 minutes)
- Refresh token: Long-lived (7 days)

Token content:
- User ID
- Roles/permissions
- Expiration timestamp
- Token ID (for revocation)

Token storage (web clients):
- Access token: Memory only (never localStorage)
- Refresh token: HttpOnly secure cookie

Token refresh flow:
1. Access token expires
2. Client sends refresh token
3. Server validates refresh token
4. Server issues new access/refresh pair
5. Old refresh token invalidated

### Session Cookies

Alternative to JWT for web applications preferring server-side sessions.

Cookie configuration:
- HttpOnly: true (not accessible to JavaScript)
- Secure: true (HTTPS only)
- SameSite: Strict or Lax
- Domain: Specific domain, not wildcard

Session storage: Redis with TTL matching session duration.

---

## Authorization

### Role-Based Access Control

Users have roles. Roles have permissions.

Standard roles:
- `admin`: Full system access
- `user`: Standard access to own resources
- `readonly`: View-only access

Permissions are fine-grained:
- `resource:create`
- `resource:read`
- `resource:update`
- `resource:delete`

### Resource Ownership

Resources belong to users or organizations. Authorization checks:
1. User authenticated
2. User has required permission
3. User owns resource or has explicit access grant

### Authorization Enforcement

Authorization is checked at the **service layer**, not the API layer. This ensures rules are enforced regardless of how the service is called (HTTP endpoint, background task, agent tool, internal API).

```python
# 1. API layer: extract user identity (thin — no authorization logic)
@router.get("/orders/{order_id}")
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession,
):
    service = OrderService(db)
    return await service.get_order(order_id, requesting_user=current_user)

# 2. Service layer: enforce authorization (all logic here)
class OrderService:
    async def get_order(self, order_id: UUID, requesting_user: User) -> OrderSchema:
        order = await self.repo.get(order_id)
        if not order:
            raise NotFoundError("Order not found")
        if order.user_id != requesting_user.id and not requesting_user.has_role("admin"):
            raise AuthorizationError("Not authorized to view this order")
        return OrderSchema.model_validate(order)

# 3. get_current_user dependency: resolves token/API key to User object
async def get_current_user(request: Request, db: DbSession) -> User:
    """Extract API key or JWT, validate, return User.
    This is the ONLY place auth tokens are parsed."""
    ...
```

**Rules:**
- API layer passes `requesting_user` to every service method that needs authorization
- Service layer checks permissions and resource ownership
- `AuthorizationError` raised in service, converted to 403 by exception handler
- Never rely on API layer alone for authorization

---

## Password Security

### Password Requirements

Minimum requirements:
- 12 characters minimum
- No maximum length
- No complexity requirements (length matters more)

Recommended: Encourage passphrase usage in UI.

### Password Storage

Passwords hashed with bcrypt:
- Work factor: 12 (adjust based on hardware)
- Each password has unique salt

Never:
- Store plaintext passwords
- Store reversibly encrypted passwords
- Log passwords or tokens

### Password Reset

Flow:
1. User requests reset via email
2. System generates time-limited token (1 hour)
3. Token sent via email (never in URL visible to logs)
4. User submits new password with token
5. Token invalidated after use
6. All existing sessions invalidated on reset

---

## API Security

### Rate Limiting

All endpoints rate limited:
- Per API key or user
- Per IP address (for unauthenticated endpoints)

Default limits:
- Authenticated: 1000 requests/minute
- Unauthenticated: 100 requests/minute
- Login endpoint: 10 requests/minute

Rate limit response: 429 Too Many Requests with Retry-After header.

### Input Validation

All inputs validated:
- Type checking (Pydantic)
- Length limits
- Format validation (email, UUID, etc.)
- Sanitization for injection prevention

Validation errors return 400 with specific field errors.

### Output Encoding

Responses properly encoded:
- JSON responses with correct Content-Type
- HTML content escaped
- User-generated content never rendered as HTML

### Request Size Limits

Maximum request body: 10MB default
Large uploads use separate upload endpoint with streaming.

---

## Network Security

### HTTPS Requirement

All production traffic over HTTPS.

Development may use HTTP for localhost only.

TLS configuration:
- Minimum TLS 1.2
- Strong cipher suites only
- HSTS headers enabled

### CORS Configuration

CORS headers configured per environment:
- Development: Allow localhost origins
- Production: Allow only production domains
- Never: Allow wildcard origins

### Security Headers

All responses include:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'self'`
- `Strict-Transport-Security: max-age=31536000`

---

## Secrets Management

### Environment Variables

Secrets passed via environment variables:
- Database credentials
- API keys for external services
- JWT signing keys
- Encryption keys

Never in:
- Code
- Configuration files in repository
- Logs

### Environment Files

`.env` files:
- Not committed to repository
- `.env.example` shows required variables (no real values)
- Different files per environment

### Rotation

Secrets should be rotatable without downtime:
- JWT keys: Support multiple active keys during rotation
- API keys: Issue new before revoking old
- Database passwords: Application handles reconnection

---

## Audit Logging

### What to Log

Security-relevant events:
- Authentication attempts (success and failure)
- Authorization failures
- Password changes
- API key creation/revocation
- Admin actions
- Data exports

### Audit Log Content

Each entry contains:
- Timestamp (UTC, microsecond precision)
- Event type
- User ID (if authenticated)
- IP address
- User agent
- Resource affected
- Outcome (success/failure)
- Additional context as needed

### Audit Log Protection

Audit logs:
- Append-only (no updates or deletes)
- Separate storage from application logs
- Retained per compliance requirements
- Access restricted to security team

---

## Vulnerability Prevention

### SQL Injection

Prevented by:
- Parameterized queries only
- ORM with parameter binding
- Never string concatenation for queries

### Cross-Site Scripting (XSS)

Prevented by:
- Output encoding in templates
- Content-Security-Policy headers
- JSON responses for API data

### Cross-Site Request Forgery (CSRF)

Prevented by:
- SameSite cookie attribute
- CSRF tokens for state-changing requests (form submissions)
- API endpoints use token auth (not vulnerable)

### Injection Attacks

General prevention:
- Validate and sanitize all inputs
- Use safe APIs (subprocess with list arguments, not shell=True)
- Escape special characters for context

---

## Incident Response

### Security Event Detection

Monitor for:
- Unusual authentication failure patterns
- API key usage from unexpected locations
- Rate limit violations
- Authorization failures

### Response Procedures

When security incident detected:
1. Assess scope and severity
2. Contain (revoke keys, block IPs as needed)
3. Investigate root cause
4. Remediate vulnerability
5. Notify affected users if data exposure
6. Post-incident review

### Disclosure

Security vulnerabilities reported via designated channel.
Response timeline:
- Acknowledge within 24 hours
- Initial assessment within 72 hours
- Fix timeline communicated
