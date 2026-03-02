# 09 - Error Codes

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic error code registry template

---

## Purpose

This document defines the error code structure and standard codes used by APIs. New error codes require registration before use.

---

## Context

API consumers need to handle errors programmatically. A 400 status code tells a client that something was wrong with the request, but not what specifically — was it a missing field, an invalid format, a duplicate entry, or a business rule violation? Consistent, machine-readable error codes let clients implement proper error handling instead of parsing human-readable error messages.

The error code structure uses the format `{CATEGORY}_{NOUN}_{STATE}` (e.g., `AUTH_TOKEN_EXPIRED`, `VAL_EMAIL_INVALID`, `RES_USER_NOT_FOUND`). The category immediately tells a developer which system is involved, the noun identifies the entity, and the state describes what went wrong. Every code maps to an HTTP status code, a human-readable message, and a recommended client action — so both humans and machines can act on the error.

This is a registry, not just a specification. New error codes must be registered in this document before use, preventing duplicate or inconsistent codes across modules. The error response envelope (`success`, `data`, `error`, `metadata`) is the same format defined in backend architecture (03), ensuring every API response — success or failure — follows a predictable structure that all clients (22) can rely on.

---

## Error Response Format

Error responses use the standard API envelope defined in **03-backend-architecture.md** (Response Format section). The `error` field contains:

| Field | Purpose |
|-------|---------|
| `code` | Machine-readable error code from the tables below |
| `message` | Human-readable description |
| `details` | Additional context (field-level errors, constraints violated) |

---

## Error Code Categories

### Authentication Errors (AUTH_*)

Errors related to identity verification.

| Code | HTTP Status | Description | Client Action |
|------|-------------|-------------|---------------|
| `AUTH_INVALID_CREDENTIALS` | 401 | Username/password incorrect | Prompt to re-enter credentials |
| `AUTH_UNAUTHORIZED` | 401 | No valid authentication | Redirect to login |
| `AUTH_API_KEY_INVALID` | 401 | API key not recognized | Prompt for new API key |
| `AUTH_API_KEY_EXPIRED` | 401 | API key has expired | Generate new key |
| `AUTH_TOKEN_EXPIRED` | 401 | JWT token has expired | Refresh token |

### Authorization Errors (AUTHZ_*)

Errors related to permission verification.

| Code | HTTP Status | Description | Client Action |
|------|-------------|-------------|---------------|
| `AUTHZ_FORBIDDEN` | 403 | Action not allowed | Display "not available" |
| `AUTHZ_INSUFFICIENT_PERMISSIONS` | 403 | User lacks permission | Show permission requirement |
| `AUTHZ_RESOURCE_ACCESS_DENIED` | 403 | No access to resource | Show access denied |

### Validation Errors (VAL_*)

Errors related to request data validation.

| Code | HTTP Status | Description | Client Action |
|------|-------------|-------------|---------------|
| `VAL_VALIDATION_ERROR` | 422 | General validation failure | Show field errors |
| `VAL_MISSING_FIELD` | 422 | Required field not provided | Highlight missing field |
| `VAL_INVALID_FORMAT` | 422 | Field format incorrect | Show format requirements |
| `VAL_INVALID_VALUE` | 422 | Field value out of range | Show valid range |

### Resource Errors (RES_*)

Errors related to resource operations.

| Code | HTTP Status | Description | Client Action |
|------|-------------|-------------|---------------|
| `RES_NOT_FOUND` | 404 | Resource does not exist | Show "not found" |
| `RES_ALREADY_EXISTS` | 409 | Resource already exists | Suggest alternative |
| `RES_CONFLICT` | 409 | State conflict | Refresh and retry |
| `RES_GONE` | 410 | Resource was deleted | Navigate away |

### System Errors (SYS_*)

Errors related to system operations.

| Code | HTTP Status | Description | Client Action |
|------|-------------|-------------|---------------|
| `SYS_INTERNAL_ERROR` | 500 | Unexpected server error | Show generic error |
| `SYS_SERVICE_UNAVAILABLE` | 503 | Service temporarily down | Show retry message |
| `SYS_DATABASE_ERROR` | 500 | Database operation failed | Show generic error |
| `SYS_EXTERNAL_SERVICE_ERROR` | 502 | Third-party service failed | Show service error |

### Rate Limiting Errors (RATE_*)

Errors related to usage limits.

| Code | HTTP Status | Description | Client Action |
|------|-------------|-------------|---------------|
| `RATE_LIMITED` | 429 | Too many requests | Show retry time |
| `RATE_QUOTA_EXCEEDED` | 429 | Usage quota exceeded | Show quota status |

### Business Logic Errors (BIZ_*)

Errors related to business rule violations.

| Code | HTTP Status | Description | Client Action |
|------|-------------|-------------|---------------|
| `BIZ_OPERATION_NOT_ALLOWED` | 400 | Operation not permitted | Explain why blocked |
| `BIZ_INVALID_STATE` | 400 | Invalid state transition | Show valid actions |
| `BIZ_PRECONDITION_FAILED` | 412 | Precondition not met | Show requirements |

---

## Exception Mapping

Backend exceptions map to error responses:

| Exception Class | Error Code | HTTP Status |
|-----------------|------------|-------------|
| `AuthenticationError` | `AUTH_UNAUTHORIZED` | 401 |
| `AuthorizationError` | `AUTHZ_FORBIDDEN` | 403 |
| `NotFoundError` | `RES_NOT_FOUND` | 404 |
| `ValidationError` | `VAL_VALIDATION_ERROR` | 422 |
| `ConflictError` | `RES_CONFLICT` | 409 |
| `RateLimitError` | `RATE_LIMITED` | 429 |
| `ExternalServiceError` | `SYS_EXTERNAL_SERVICE_ERROR` | 502 |
| `DatabaseError` | `SYS_DATABASE_ERROR` | 500 |

---

## Client Implementation Guide

### Error Handling Pattern

```typescript
async function apiCall<T>(endpoint: string): Promise<T> {
  const response = await fetch(endpoint);
  const data = await response.json();
  
  if (!data.success) {
    handleError(data.error, data.metadata.request_id);
    throw new ApiError(data.error);
  }
  
  return data.data;
}

function handleError(error: ApiError, requestId: string) {
  switch (error.code) {
    case 'AUTH_UNAUTHORIZED':
    case 'AUTH_API_KEY_INVALID':
    case 'AUTH_TOKEN_EXPIRED':
      redirectToLogin();
      break;
      
    case 'AUTHZ_FORBIDDEN':
    case 'AUTHZ_INSUFFICIENT_PERMISSIONS':
      showPermissionError(error.message);
      break;
      
    case 'VAL_VALIDATION_ERROR':
    case 'VAL_MISSING_FIELD':
    case 'VAL_INVALID_FORMAT':
      showFieldErrors(error.details);
      break;
      
    case 'RES_NOT_FOUND':
      showNotFound(error.message);
      break;
      
    case 'RATE_LIMITED':
      showRateLimitMessage();
      break;
      
    default:
      showGenericError(requestId);
  }
}
```

### CLI Error Handling

```python
def handle_api_error(error: dict, request_id: str) -> None:
    code = error.get('code', 'UNKNOWN')
    message = error.get('message', 'An error occurred')
    
    if code.startswith('AUTH_'):
        click.echo(click.style('Authentication required.', fg='red'))
        sys.exit(1)
        
    if code.startswith('AUTHZ_'):
        click.echo(click.style(f'Permission denied: {message}', fg='red'))
        sys.exit(1)
        
    if code == 'RES_NOT_FOUND':
        click.echo(click.style(f'Not found: {message}', fg='yellow'))
        sys.exit(1)
        
    if code == 'RATE_LIMITED':
        click.echo(click.style('Rate limit exceeded. Please wait.', fg='yellow'))
        sys.exit(1)
        
    # Default: show error with request ID
    click.echo(click.style(f'Error: {message}', fg='red'))
    click.echo(click.style(f'Request ID: {request_id}', fg='dim'))
    sys.exit(1)
```

---

## Adding New Error Codes

### Requirements

1. **Register here first**: Add to this document before using in code
2. **Follow naming convention**: `CATEGORY_DESCRIPTION` in UPPER_SNAKE_CASE
3. **Assign HTTP status**: Map to appropriate status code
4. **Document client action**: Specify what clients should do
5. **Update exception mapping**: If new exception class needed

### Naming Convention

```
{CATEGORY}_{NOUN}_{STATE}

Examples:
- AUTH_TOKEN_EXPIRED (not TOKEN_AUTH_EXPIRED)
- VAL_EMAIL_INVALID (not INVALID_EMAIL)
- RES_PROJECT_ARCHIVED (not PROJECT_IS_ARCHIVED)
```

### Categories

| Prefix | Purpose |
|--------|---------|
| `AUTH_` | Authentication (identity verification) |
| `AUTHZ_` | Authorization (permission verification) |
| `VAL_` | Validation (input verification) |
| `RES_` | Resource (CRUD operations) |
| `SYS_` | System (infrastructure) |
| `RATE_` | Rate limiting (usage limits) |
| `BIZ_` | Business logic (domain rules) |

---

## Domain-Specific Error Codes

Add domain-specific error codes as needed. Examples:

### Example: E-commerce Domain

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `ORDER_ALREADY_SHIPPED` | 400 | Cannot modify shipped order |
| `ORDER_PAYMENT_FAILED` | 402 | Payment processing failed |
| `INVENTORY_INSUFFICIENT` | 409 | Not enough stock |

### Example: User Management Domain

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `USER_EMAIL_EXISTS` | 409 | Email already registered |
| `USER_USERNAME_EXISTS` | 409 | Username already taken |
| `USER_ACCOUNT_LOCKED` | 403 | Account locked after failed attempts |

---

## Deprecation Process

To deprecate an error code:

1. Add `@deprecated` note with removal version
2. Log warning when deprecated code is returned
3. Update client documentation
4. Remove after two minor versions
