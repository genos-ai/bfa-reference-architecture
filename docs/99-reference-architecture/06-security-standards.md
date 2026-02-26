# 06 - Security Standards

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-02-11*

## Changelog

- 1.0.0 (2026-02-11): Initial security standards based on OWASP ASVS 5.0 and Top 10:2025

---

## Purpose

This document defines security standards for application development. It complements 05-authentication.md (which covers authentication and authorization) and 07-data-protection.md (which covers privacy and PII handling).

Security is not optional. Every requirement in this document applies to all projects.

---

## Context

Security vulnerabilities are the highest-impact bugs a system can have — a single flaw can expose user data, enable unauthorized access, or compromise the entire infrastructure. This document exists because security must be designed in from the start, not bolted on after an audit or a breach. It provides prescriptive standards aligned with OWASP ASVS 5.0 and the OWASP Top 10:2025.

The organizing principle is defense in depth: no single security control is trusted in isolation. Network-layer controls (TLS, firewalls), application-layer controls (authentication, input validation), and data-layer controls (encryption, access logging) each provide independent protection. If one layer fails, others still protect the system. The document maps every OWASP Top 10 risk to the specific document and section where it is addressed, so nothing falls through the cracks.

Approved cryptographic algorithms, rate limiting thresholds, security headers, and supply chain security rules are defined explicitly because "use appropriate security measures" is not actionable guidance. This document complements authentication (09) for access control, data protection (18) for privacy and PII handling, and observability (12) for security logging and alerting.

---

## OWASP Top 10:2025 Mapping

| OWASP Risk | Where Addressed |
|------------|-----------------|
| Broken Access Control | 05-authentication.md (Authorization) |
| Security Misconfiguration | This document (Configuration Security) |
| Software Supply Chain Failures | This document (Supply Chain Security) |
| Cryptographic Failures | This document (Cryptographic Standards) |
| Injection | This document (Input Handling) |
| Insecure Design | This document (Secure Design Principles) |
| Authentication Failures | 05-authentication.md |
| Software or Data Integrity Failures | This document (Integrity Verification) |
| Security Logging and Alerting Failures | 10-observability.md, 05-authentication.md (Audit Logging) |
| Mishandling of Exceptional Conditions | 09-error-codes.md, This document (Error Handling) |

---

## Secure Design Principles

### Defense in Depth

Never rely on a single security control. Layer defenses:

1. **Network layer**: Firewall, TLS, IP allowlisting
2. **Application layer**: Authentication, authorization, input validation
3. **Data layer**: Encryption at rest, access controls, audit logging

If one layer fails, others still protect the system.

### Least Privilege

Grant minimum permissions required:

- Database users have only necessary table/operation access
- API keys are scoped to specific operations
- Service accounts have limited permissions
- File system access restricted to required paths

### Fail Secure

When errors occur, fail to a secure state:

```python
# Correct: Deny by default
def check_permission(user, resource):
    try:
        return permission_service.has_access(user, resource)
    except Exception:
        logger.error("Permission check failed", exc_info=True)
        return False  # Deny on error

# Wrong: Allow on error
def check_permission_bad(user, resource):
    try:
        return permission_service.has_access(user, resource)
    except Exception:
        return True  # NEVER do this
```

### Secure by Default

Default configurations must be secure:

- Authentication required by default (opt-out for public endpoints)
- HTTPS enforced by default
- Strict CORS by default
- Security headers enabled by default

---

## Cryptographic Standards

### Approved Algorithms

| Purpose | Algorithm | Key Size | Notes |
|---------|-----------|----------|-------|
| Password hashing | bcrypt | work factor 12+ | Adjust for ~250ms hash time |
| Password hashing (alternative) | Argon2id | memory 64MB, iterations 3 | Preferred for new systems |
| Symmetric encryption | AES-256-GCM | 256-bit | Authenticated encryption required |
| Asymmetric encryption | RSA | 2048-bit minimum | 4096-bit for long-term keys |
| Asymmetric encryption (preferred) | Ed25519 | 256-bit | Preferred for new systems |
| Hashing (non-password) | SHA-256 | - | SHA-512 for high-security |
| HMAC | HMAC-SHA-256 | 256-bit key | For message authentication |
| Random generation | `secrets` module | - | Never use `random` for security |

### Deprecated Algorithms (Do Not Use)

- MD5 (any purpose)
- SHA-1 (any purpose)
- DES, 3DES
- RC4
- RSA < 2048-bit
- PKCS#1 v1.5 padding

### Key Management

**Generation:**
```python
import secrets

# API keys, tokens
token = secrets.token_urlsafe(32)  # 256 bits

# Encryption keys
key = secrets.token_bytes(32)  # 256 bits for AES-256
```

**Storage:**
- Never in code or version control
- Environment variables for runtime secrets
- Secrets manager for production (HashiCorp Vault, AWS Secrets Manager)
- Encrypted at rest if stored in database

**Rotation:**
- JWT signing keys: Support multiple active keys during rotation
- Encryption keys: Re-encrypt data with new key, maintain old key for decryption during transition
- API keys: Issue new before revoking old
- Document rotation procedures for each key type

---

## Input Handling

### Validation Strategy

All input is untrusted. Validate at the boundary:

```python
from pydantic import BaseModel, Field, field_validator
import re

class UserInput(BaseModel):
    # Type validation
    user_id: UUID
    
    # Length limits
    username: str = Field(min_length=3, max_length=50)
    
    # Format validation
    email: EmailStr
    
    # Custom validation
    phone: str = Field(pattern=r"^\+?[1-9]\d{1,14}$")
    
    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username contains invalid characters")
        return v
```

### SQL Injection Prevention

Always use parameterized queries:

```python
# Correct: Parameterized query
result = await session.execute(
    select(User).where(User.email == email)
)

# Correct: Raw SQL with parameters
result = await session.execute(
    text("SELECT * FROM users WHERE email = :email"),
    {"email": email}
)

# WRONG: String concatenation
result = await session.execute(
    text(f"SELECT * FROM users WHERE email = '{email}'")  # NEVER
)
```

### Command Injection Prevention

Never use shell=True with user input:

```python
import subprocess

# Correct: List arguments
subprocess.run(["ls", "-la", user_path], check=True)

# WRONG: Shell with user input
subprocess.run(f"ls -la {user_path}", shell=True)  # NEVER
```

### Path Traversal Prevention

Validate and sanitize file paths:

```python
from pathlib import Path

UPLOAD_DIR = Path("/app/uploads")

def safe_path(filename: str) -> Path:
    # Remove path separators
    safe_name = Path(filename).name
    
    # Resolve and verify within allowed directory
    full_path = (UPLOAD_DIR / safe_name).resolve()
    
    if not full_path.is_relative_to(UPLOAD_DIR):
        raise ValueError("Invalid path")
    
    return full_path
```

### XSS Prevention

For API backends returning JSON:
- Set `Content-Type: application/json`
- Never render user input as HTML
- Escape if embedding in HTML responses

For any HTML rendering:
- Use templating engine with auto-escaping (Jinja2 with autoescape=True)
- Sanitize HTML input with allowlist (bleach library)
- Set Content-Security-Policy headers

---

## File Upload Security

### Validation Requirements

```python
import magic
from pathlib import Path

ALLOWED_TYPES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "application/pdf": [".pdf"],
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

async def validate_upload(file: UploadFile) -> None:
    # Check file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise ValueError(f"File exceeds {MAX_FILE_SIZE} bytes")
    
    # Check MIME type (content-based, not extension)
    mime_type = magic.from_buffer(content, mime=True)
    if mime_type not in ALLOWED_TYPES:
        raise ValueError(f"File type {mime_type} not allowed")
    
    # Verify extension matches content
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_TYPES[mime_type]:
        raise ValueError("File extension does not match content")
    
    # Reset file position
    await file.seek(0)
```

### Storage Requirements

- Store outside web root
- Generate random filenames (never use user-provided names directly)
- Scan for malware before processing
- Set restrictive permissions (read-only for application)

---

## API Security

### Endpoint Protection

```python
from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Public endpoint (explicit)
@router.get("/public/health")
async def health():
    return {"status": "ok"}

# Protected endpoint (default)
@router.get("/users/me")
async def get_current_user(
    api_key: str = Security(api_key_header),
    user: User = Depends(get_current_user),
):
    return user
```

### Rate Limiting

Implement rate limiting at multiple levels:

| Level | Limit | Window | Action |
|-------|-------|--------|--------|
| Global | 10,000 req | 1 minute | 503 Service Unavailable |
| Per IP (unauthenticated) | 100 req | 1 minute | 429 Too Many Requests |
| Per User (authenticated) | 1,000 req | 1 minute | 429 Too Many Requests |
| Login endpoint | 10 req | 1 minute | 429 + exponential backoff |
| Password reset | 3 req | 1 hour | 429 + account lockout warning |

### Request Size Limits

```python
from fastapi import FastAPI

app = FastAPI()

# Global limit
app.add_middleware(
    # Limit request body size
    # Implementation depends on deployment (nginx, uvicorn, etc.)
)

# Per-endpoint limit for file uploads
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(..., max_length=10_000_000)  # 10MB
):
    pass
```

### Webhook Security

For incoming webhooks:
- Verify signature (HMAC with shared secret)
- Validate source IP if known
- Use idempotency keys
- Process asynchronously (don't block on webhook handler)

```python
import hmac
import hashlib

def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str,
) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

---

## Supply Chain Security

### Dependency Management

**Requirements:**
- Pin exact versions in production (`package==1.2.3`, not `package>=1.2.3`)
- Use lockfiles (`requirements.txt` with hashes, `poetry.lock`, `uv.lock`)
- Review dependency changes in pull requests
- Audit dependencies regularly

**Lockfile with hashes:**
```bash
# Generate with pip-tools
pip-compile --generate-hashes requirements.in

# Or with pip
pip freeze > requirements.txt
pip hash <package>.whl >> requirements.txt
```

### Vulnerability Scanning

Run security scans in CI/CD:

```yaml
# Example CI step
- name: Security scan
  run: |
    pip install safety pip-audit
    safety check --full-report
    pip-audit --strict
```

**Scan frequency:**
- Every pull request
- Daily on main branch
- Immediately when CVE announced for used package

### Software Bill of Materials (SBOM)

Generate SBOM for deployments:

```bash
# Generate SBOM
pip install cyclonedx-bom
cyclonedx-py -o sbom.json
```

Store SBOM with each release for audit trail.

---

## Configuration Security

### Environment Separation

| Setting | Development | Staging | Production |
|---------|-------------|---------|------------|
| Debug mode | Enabled | Disabled | Disabled |
| API docs | Enabled | Enabled | Disabled |
| Verbose errors | Enabled | Disabled | Disabled |
| CORS origins | localhost | staging domain | production domain only |
| TLS | Optional | Required | Required |
| Rate limiting | Relaxed | Production-like | Strict |

### Secrets Checklist

Before deployment, verify:

- [ ] No secrets in code or config files
- [ ] No default passwords or keys
- [ ] All secrets loaded from environment or secrets manager
- [ ] Secrets are not logged
- [ ] `.env` files are in `.gitignore`
- [ ] CI/CD secrets are properly scoped

### Security Headers

Configure in middleware or reverse proxy:

```python
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response
```

---

## Integrity Verification

### Code Integrity

- Sign commits with GPG
- Require signed commits for protected branches
- Verify signatures in CI/CD

### Artifact Integrity

- Generate checksums for build artifacts
- Verify checksums before deployment
- Use signed container images

```bash
# Generate checksum
sha256sum app.tar.gz > app.tar.gz.sha256

# Verify checksum
sha256sum -c app.tar.gz.sha256
```

### Data Integrity

For sensitive data:
- Use HMAC to detect tampering
- Store hash alongside data
- Verify on read

---

## Error Handling Security

### Safe Error Messages

Never expose internal details in error responses:

```python
# Correct: Generic message
{
    "error": {
        "code": "AUTH_INVALID_CREDENTIALS",
        "message": "Invalid username or password"
    }
}

# WRONG: Information disclosure
{
    "error": {
        "message": "User admin@example.com not found in database users table"
    }
}
```

### Exception Handling

```python
from fastapi import HTTPException
import traceback

async def process_request(data: dict):
    try:
        return await business_logic(data)
    except ValidationError as e:
        # Safe to expose validation errors
        raise HTTPException(status_code=422, detail=str(e))
    except NotFoundError:
        # Generic not found
        raise HTTPException(status_code=404, detail="Resource not found")
    except Exception:
        # Log full error internally
        logger.exception("Unexpected error processing request")
        # Return generic error to client
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Timing Attack Prevention

Use constant-time comparison for secrets:

```python
import hmac

# Correct: Constant-time comparison
def verify_token(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided, expected)

# WRONG: Variable-time comparison
def verify_token_bad(provided: str, expected: str) -> bool:
    return provided == expected  # Vulnerable to timing attack
```

---

## Security Testing

### Required Testing

| Test Type | Frequency | Tools |
|-----------|-----------|-------|
| Static Analysis (SAST) | Every commit | bandit, semgrep |
| Dependency Scan | Every commit | safety, pip-audit |
| Secret Detection | Every commit | detect-secrets, gitleaks |
| Dynamic Analysis (DAST) | Weekly / Pre-release | OWASP ZAP |
| Penetration Testing | Annually | External firm |

### SAST Configuration

```yaml
# .bandit.yaml
exclude_dirs:
  - tests
  - venv

skips:
  - B101  # assert_used (OK in tests)

# Run: bandit -r modules/ -c .bandit.yaml
```

### Secret Detection

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

---

## Security Incident Checklist

When a security issue is discovered:

1. **Assess** - Determine scope and severity
2. **Contain** - Revoke compromised credentials, block attack vectors
3. **Preserve** - Capture logs and evidence before they rotate
4. **Investigate** - Determine root cause and full impact
5. **Remediate** - Fix vulnerability, deploy patches
6. **Notify** - Inform affected users if data exposed
7. **Review** - Post-incident analysis, update procedures

Document all incidents and responses for compliance and learning.

---

## Compliance Considerations

This document provides technical security controls. For specific compliance frameworks:

| Framework | Additional Requirements |
|-----------|------------------------|
| SOC 2 | Access reviews, change management, vendor management |
| GDPR | See 07-data-protection.md |
| HIPAA | PHI handling, BAAs, additional audit requirements |
| PCI DSS | Cardholder data isolation, quarterly scans |

Consult compliance specialists for framework-specific requirements.
