# 07 - Data Protection

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-02-11*

## Changelog

- 1.0.0 (2026-02-11): Initial data protection and privacy standards

---

## Purpose

This document defines standards for handling personal data, ensuring privacy compliance, and protecting sensitive information. It complements 05-authentication.md (access control) and 06-security-standards.md (technical security controls).

These standards apply to any system that collects, processes, or stores personal data.

---

## Context

Applications that handle personal data carry legal and ethical obligations. GDPR, CCPA, HIPAA, and PCI DSS all impose specific requirements on how personal data is collected, stored, processed, and deleted. Failing to meet these requirements results in regulatory fines, legal liability, and destruction of user trust — consequences that far exceed the cost of building compliance in from the start.

This document solves the problem by classifying all data into four levels (Public, Internal, Confidential, Restricted) and defining handling rules for each: what encryption is required, who can access it, how long it is retained, and how it is disposed of. The key insight is that data protection must be embedded in the data model itself — classification metadata on database columns, field-level encryption for sensitive attributes, and retention policies enforced automatically rather than manually.

The document also standardizes data subject rights (access, erasure, rectification, portability) and breach response procedures, because these are operational capabilities that must be built into the system, not improvised during an incident. This module complements authentication (05) for access control enforcement and security standards (06) for the underlying technical controls.

---

## Data Classification

### Classification Levels

| Level | Description | Examples | Handling |
|-------|-------------|----------|----------|
| **Public** | No restrictions | Marketing content, public docs | Standard handling |
| **Internal** | Business use only | Internal reports, aggregated metrics | Access controls |
| **Confidential** | Restricted access | User data, business data | Encryption, audit logging |
| **Restricted** | Highly sensitive | Passwords, payment data, health data | Encryption, strict access, retention limits |

### Personal Data Categories

| Category | Examples | Classification |
|----------|----------|----------------|
| **Identifiers** | Name, email, phone, address | Confidential |
| **Account Data** | Username, preferences, settings | Confidential |
| **Authentication** | Passwords, API keys, tokens | Restricted |
| **Financial** | Payment cards, bank accounts | Restricted |
| **Health** | Medical records, health status | Restricted |
| **Biometric** | Fingerprints, facial recognition | Restricted |
| **Location** | GPS coordinates, IP addresses | Confidential |
| **Behavioral** | Usage patterns, preferences | Confidential |

### Classification in Code

Document data classification in models:

```python
from sqlalchemy import Column, String, Text
from sqlalchemy.orm import Mapped, mapped_column

class User(Base):
    """
    User account data.
    
    Data Classification: Confidential
    Retention: Account lifetime + 30 days
    PII Fields: email, name, phone
    """
    __tablename__ = "users"
    
    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)  # PII
    name: Mapped[str] = mapped_column(String(100))  # PII
    phone: Mapped[str | None] = mapped_column(String(20))  # PII
    preferences: Mapped[dict] = mapped_column(JSON, default={})
```

---

## Data Collection

### Minimization Principle

Collect only data necessary for the stated purpose:

```python
# Correct: Collect only what's needed
class RegistrationRequest(BaseModel):
    email: EmailStr
    password: str
    
# Wrong: Collecting unnecessary data
class RegistrationRequestBad(BaseModel):
    email: EmailStr
    password: str
    phone: str  # Not needed for registration
    date_of_birth: date  # Not needed for registration
    gender: str  # Not needed for registration
```

### Purpose Specification

Document why each piece of data is collected:

```python
class UserProfile(BaseModel):
    """
    User profile information.
    
    Purpose: Account identification and communication
    Legal Basis: Contract performance (account creation)
    """
    email: EmailStr  # Purpose: Account login, notifications
    name: str  # Purpose: Personalization, communication
    timezone: str  # Purpose: Display times correctly
```

### Consent Requirements

For data not essential to service:

```python
class MarketingPreferences(BaseModel):
    """
    Optional marketing preferences.
    
    Legal Basis: Consent (opt-in required)
    """
    email_marketing: bool = False  # Default opt-out
    analytics_tracking: bool = False  # Default opt-out
    consent_timestamp: datetime | None = None
    consent_source: str | None = None  # Where consent was given
```

---

## Data Storage

### Encryption at Rest

Encrypt sensitive data before storage:

```python
from cryptography.fernet import Fernet

class EncryptedField:
    """
    Encrypt sensitive fields before database storage.
    
    Use for: SSN, payment details, health information
    Do not use for: Fields that need indexing or searching
    """
    
    def __init__(self, key: bytes):
        self.cipher = Fernet(key)
    
    def encrypt(self, value: str) -> bytes:
        return self.cipher.encrypt(value.encode())
    
    def decrypt(self, encrypted: bytes) -> str:
        return self.cipher.decrypt(encrypted).decode()
```

### Database-Level Encryption

For highly sensitive data, use database encryption:

```sql
-- PostgreSQL: Enable encryption extension
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Encrypt on insert
INSERT INTO sensitive_data (id, ssn_encrypted)
VALUES (
    gen_random_uuid(),
    pgp_sym_encrypt('123-45-6789', 'encryption_key')
);

-- Decrypt on select
SELECT pgp_sym_decrypt(ssn_encrypted::bytea, 'encryption_key')
FROM sensitive_data;
```

### Tokenization

For payment data, use tokenization instead of storage:

```python
# Never store raw card numbers
# Use payment processor tokens

class PaymentMethod(Base):
    """
    Stored payment method.
    
    Note: We store processor tokens, never raw card data.
    """
    __tablename__ = "payment_methods"
    
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    processor_token: Mapped[str]  # Stripe/Braintree token
    last_four: Mapped[str]  # For display only
    card_type: Mapped[str]  # visa, mastercard, etc.
    expiry_month: Mapped[int]
    expiry_year: Mapped[int]
    # Never: card_number, cvv, full_expiry
```

---

## Data Access

### Access Control Matrix

Define who can access what data:

| Role | Public | Internal | Confidential | Restricted |
|------|--------|----------|--------------|------------|
| Anonymous | Read | - | - | - |
| User | Read | - | Own data only | Own data only |
| Support | Read | Read | Read (logged) | - |
| Admin | Read | Read/Write | Read/Write (logged) | Read (logged, approved) |
| System | Read | Read/Write | Read/Write | Read/Write |

### Implementing Access Control

```python
from enum import Enum
from functools import wraps

class DataClassification(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

def requires_classification(classification: DataClassification):
    """Decorator to enforce data access controls."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, user: User, **kwargs):
            if not can_access(user, classification):
                logger.warning(
                    "Unauthorized data access attempt",
                    extra={
                        "user_id": str(user.id),
                        "classification": classification.value,
                        "function": func.__name__,
                    }
                )
                raise AuthorizationError("Insufficient permissions")
            
            # Log access to sensitive data
            if classification in (DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED):
                logger.info(
                    "Sensitive data accessed",
                    extra={
                        "user_id": str(user.id),
                        "classification": classification.value,
                        "function": func.__name__,
                    }
                )
            
            return await func(*args, user=user, **kwargs)
        return wrapper
    return decorator

@requires_classification(DataClassification.RESTRICTED)
async def get_user_ssn(user_id: UUID, user: User) -> str:
    """Retrieve user SSN. Restricted access, fully audited."""
    pass
```

### Audit Trail

Log all access to sensitive data:

```python
class DataAccessLog(Base):
    """
    Audit log for sensitive data access.
    
    Retention: 7 years (compliance requirement)
    """
    __tablename__ = "data_access_logs"
    
    id: Mapped[UUID] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(default=utc_now)
    accessor_id: Mapped[UUID]  # Who accessed
    accessor_type: Mapped[str]  # user, admin, system
    resource_type: Mapped[str]  # Table/model accessed
    resource_id: Mapped[UUID]  # Record accessed
    action: Mapped[str]  # read, write, delete
    classification: Mapped[str]  # Data classification level
    ip_address: Mapped[str]
    user_agent: Mapped[str]
    justification: Mapped[str | None]  # Required for restricted data
```

---

## Data Retention

### Retention Policy

| Data Type | Retention Period | After Expiry |
|-----------|------------------|--------------|
| Active user data | Account lifetime | Delete or anonymize |
| Deleted user data | 30 days | Hard delete |
| Authentication logs | 90 days | Delete |
| Audit logs | 7 years | Archive, then delete |
| Payment records | 7 years (legal) | Archive, then delete |
| Analytics (identified) | 90 days | Anonymize |
| Analytics (anonymous) | Indefinite | N/A |
| Backups | 30 days | Rotate out |

### Implementing Retention

```python
from datetime import timedelta

class RetentionPolicy:
    """Data retention configuration."""
    
    POLICIES = {
        "user_data": timedelta(days=30),  # After account deletion
        "auth_logs": timedelta(days=90),
        "audit_logs": timedelta(days=2555),  # 7 years
        "analytics": timedelta(days=90),
    }
    
    @classmethod
    async def cleanup_expired(cls, session: AsyncSession) -> dict[str, int]:
        """Remove data past retention period."""
        results = {}
        
        # Soft-deleted users past retention
        cutoff = utc_now() - cls.POLICIES["user_data"]
        deleted = await session.execute(
            delete(User)
            .where(User.deleted_at < cutoff)
            .where(User.deleted_at.isnot(None))
        )
        results["users"] = deleted.rowcount
        
        # Old auth logs
        cutoff = utc_now() - cls.POLICIES["auth_logs"]
        deleted = await session.execute(
            delete(AuthLog).where(AuthLog.timestamp < cutoff)
        )
        results["auth_logs"] = deleted.rowcount
        
        await session.commit()
        return results
```

### Scheduled Cleanup

```python
# Run daily via cron or task scheduler
async def daily_retention_cleanup():
    """Daily job to enforce retention policies."""
    async with get_session() as session:
        results = await RetentionPolicy.cleanup_expired(session)
        logger.info("Retention cleanup completed", extra=results)
```

---

## Data Subject Rights

### Right to Access (Data Export)

```python
async def export_user_data(user_id: UUID) -> dict:
    """
    Export all data for a user (GDPR Article 15).
    
    Returns machine-readable format (JSON).
    """
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise NotFoundError("User not found")
        
        export = {
            "export_date": utc_now().isoformat(),
            "user_id": str(user_id),
            "profile": {
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at.isoformat(),
            },
            "preferences": user.preferences,
            "activity": await get_user_activity(session, user_id),
            "data_shared_with": await get_third_party_sharing(session, user_id),
        }
        
        # Log the export request
        logger.info("User data exported", extra={"user_id": str(user_id)})
        
        return export
```

### Right to Erasure (Deletion)

```python
async def delete_user_data(user_id: UUID, hard_delete: bool = False) -> None:
    """
    Delete user data (GDPR Article 17).
    
    Args:
        user_id: User to delete
        hard_delete: If True, immediate deletion. If False, soft delete with retention period.
    """
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise NotFoundError("User not found")
        
        if hard_delete:
            # Immediate deletion - use for GDPR requests
            await session.delete(user)
            # Also delete related data
            await session.execute(
                delete(UserActivity).where(UserActivity.user_id == user_id)
            )
        else:
            # Soft delete - standard account deletion
            user.deleted_at = utc_now()
            user.email = f"deleted_{user_id}@deleted.local"  # Anonymize
            user.name = "Deleted User"
        
        await session.commit()
        
        logger.info(
            "User data deleted",
            extra={"user_id": str(user_id), "hard_delete": hard_delete}
        )
```

### Right to Rectification (Update)

```python
async def update_user_data(
    user_id: UUID,
    updates: dict,
    requester: User,
) -> User:
    """
    Update user data (GDPR Article 16).
    
    Logs all changes for audit trail.
    """
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise NotFoundError("User not found")
        
        # Log what changed
        changes = {}
        for field, new_value in updates.items():
            old_value = getattr(user, field, None)
            if old_value != new_value:
                changes[field] = {"old": old_value, "new": new_value}
                setattr(user, field, new_value)
        
        if changes:
            logger.info(
                "User data updated",
                extra={
                    "user_id": str(user_id),
                    "requester_id": str(requester.id),
                    "fields_changed": list(changes.keys()),
                }
            )
        
        await session.commit()
        return user
```

### Right to Portability

```python
async def export_portable_data(user_id: UUID) -> bytes:
    """
    Export data in portable format (GDPR Article 20).
    
    Returns: JSON file as bytes
    """
    data = await export_user_data(user_id)
    
    # Standard JSON format for portability
    return json.dumps(data, indent=2, default=str).encode()
```

---

## Data Anonymization

### Anonymization Techniques

| Technique | Use Case | Example |
|-----------|----------|---------|
| **Deletion** | Remove entirely | Delete email field |
| **Masking** | Partial visibility | `john@****.com` |
| **Generalization** | Reduce precision | Age 25 → Age range 20-30 |
| **Pseudonymization** | Replace with token | User ID → Random UUID |
| **Aggregation** | Combine records | Individual → Group statistics |

### Implementation

```python
import hashlib
from typing import Any

class Anonymizer:
    """Utilities for data anonymization."""
    
    @staticmethod
    def mask_email(email: str) -> str:
        """Mask email for display: john@example.com → j***@e***.com"""
        local, domain = email.split("@")
        domain_parts = domain.split(".")
        return f"{local[0]}***@{domain_parts[0][0]}***.{domain_parts[-1]}"
    
    @staticmethod
    def mask_phone(phone: str) -> str:
        """Mask phone: +1234567890 → +1******890"""
        if len(phone) < 4:
            return "***"
        return f"{phone[:2]}******{phone[-3:]}"
    
    @staticmethod
    def pseudonymize(value: str, salt: str) -> str:
        """Create consistent pseudonym for value."""
        return hashlib.sha256(f"{salt}{value}".encode()).hexdigest()[:16]
    
    @staticmethod
    def generalize_age(age: int) -> str:
        """Convert exact age to range."""
        if age < 18:
            return "under_18"
        elif age < 25:
            return "18-24"
        elif age < 35:
            return "25-34"
        elif age < 45:
            return "35-44"
        elif age < 55:
            return "45-54"
        elif age < 65:
            return "55-64"
        else:
            return "65+"

async def anonymize_for_analytics(user: User) -> dict:
    """Prepare user data for analytics (anonymized)."""
    return {
        "user_pseudo_id": Anonymizer.pseudonymize(str(user.id), ANALYTICS_SALT),
        "age_range": Anonymizer.generalize_age(user.age) if user.age else None,
        "country": user.country,  # Keep for geo analytics
        "created_month": user.created_at.strftime("%Y-%m"),  # Reduce precision
    }
```

---

## Third-Party Data Sharing

### Sharing Requirements

Before sharing data with third parties:

1. **Document the recipient** - Who receives data
2. **Define the purpose** - Why they need it
3. **Establish legal basis** - Contract, consent, or legitimate interest
4. **Implement safeguards** - DPA, encryption, access controls
5. **Enable audit** - Log all data transfers

### Data Processing Agreement (DPA)

Required elements for any third-party processor:

- Purpose limitation
- Data security requirements
- Subprocessor restrictions
- Audit rights
- Data deletion on termination
- Breach notification requirements

### Logging Third-Party Transfers

```python
class DataTransferLog(Base):
    """Log all data transfers to third parties."""
    __tablename__ = "data_transfer_logs"
    
    id: Mapped[UUID] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(default=utc_now)
    recipient: Mapped[str]  # Third party name
    purpose: Mapped[str]  # Why data was shared
    data_types: Mapped[list[str]]  # What was shared
    record_count: Mapped[int]  # How many records
    user_ids: Mapped[list[UUID] | None]  # Affected users (if applicable)
    legal_basis: Mapped[str]  # consent, contract, etc.
    transfer_id: Mapped[str]  # For tracing
```

---

## Breach Response

### Breach Classification

| Severity | Criteria | Response Time |
|----------|----------|---------------|
| **Critical** | Restricted data exposed, large scale | Immediate |
| **High** | Confidential data exposed | 24 hours |
| **Medium** | Internal data exposed | 72 hours |
| **Low** | Public data affected | 1 week |

### Notification Requirements

**Regulatory notification** (where required):
- Within 72 hours of discovery
- Include: Nature of breach, data affected, likely consequences, mitigation measures

**User notification** (when high risk):
- Without undue delay
- Clear language describing what happened
- What data was affected
- What actions users should take
- Contact information for questions

### Breach Response Template

```python
@dataclass
class BreachReport:
    """Structure for documenting data breaches."""
    
    # Discovery
    discovered_at: datetime
    discovered_by: str
    discovery_method: str
    
    # Scope
    data_types_affected: list[str]
    classification_level: str
    estimated_records: int
    affected_users: list[UUID] | None
    
    # Cause
    root_cause: str
    attack_vector: str | None
    
    # Response
    containment_actions: list[str]
    remediation_actions: list[str]
    notification_required: bool
    notification_sent_at: datetime | None
    
    # Follow-up
    lessons_learned: str
    preventive_measures: list[str]
```

---

## Privacy by Design Checklist

For every new feature handling personal data:

### Planning Phase
- [ ] What personal data is collected?
- [ ] Why is each data point necessary?
- [ ] What is the legal basis for processing?
- [ ] How long will data be retained?
- [ ] Who will have access?

### Implementation Phase
- [ ] Data classification documented in code
- [ ] Encryption implemented for sensitive fields
- [ ] Access controls enforced
- [ ] Audit logging enabled
- [ ] Retention automation configured

### Testing Phase
- [ ] Data export functionality works
- [ ] Data deletion removes all instances
- [ ] Access controls tested
- [ ] Audit logs capture all access

### Deployment Phase
- [ ] Privacy policy updated if needed
- [ ] User consent flows updated if needed
- [ ] Third-party DPAs in place if sharing
- [ ] Monitoring for unauthorized access

---

## Compliance Reference

| Regulation | Key Requirements | Documentation |
|------------|------------------|---------------|
| **GDPR** | Consent, data subject rights, DPAs, breach notification | This document |
| **CCPA/CPRA** | Right to know, delete, opt-out of sale | This document |
| **HIPAA** | PHI safeguards, BAAs, access controls | Additional controls required |
| **PCI DSS** | Cardholder data protection | 06-security-standards.md + additional |
| **SOC 2** | Security, availability, confidentiality | 06-security-standards.md + policies |

For specific compliance requirements, consult legal and compliance teams.
