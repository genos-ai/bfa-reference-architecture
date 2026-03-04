"""
Custom Exceptions.

Application-specific exception classes for consistent error handling.
"""


class ApplicationError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, code: str = "SYS_INTERNAL_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(self.message)


class NotFoundError(ApplicationError):
    """Raised when a resource cannot be found."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, code="RES_NOT_FOUND")


class ValidationError(ApplicationError):
    """Raised when validation fails."""

    def __init__(self, message: str = "Validation failed", details: dict | None = None) -> None:
        self.details = details or {}
        super().__init__(message, code="VAL_VALIDATION_ERROR")


class AuthenticationError(ApplicationError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, code="AUTH_UNAUTHORIZED")


class AuthorizationError(ApplicationError):
    """Raised when authorization fails."""

    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message, code="AUTHZ_FORBIDDEN")


class ConflictError(ApplicationError):
    """Raised when there is a state conflict."""

    def __init__(self, message: str = "Resource conflict") -> None:
        super().__init__(message, code="RES_CONFLICT")


class ExternalServiceError(ApplicationError):
    """Raised when an external service call fails."""

    def __init__(self, message: str = "External service error") -> None:
        super().__init__(message, code="SYS_EXTERNAL_SERVICE_ERROR")


class RateLimitError(ApplicationError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message, code="RATE_LIMITED")


class BudgetExceededError(ApplicationError):
    """Raised when a session's cost budget is exceeded."""

    def __init__(
        self,
        message: str = "Cost budget exceeded",
        current_cost: float = 0.0,
        budget: float = 0.0,
    ) -> None:
        self.current_cost = current_cost
        self.budget = budget
        super().__init__(message, code="COST_BUDGET_EXCEEDED")


class DatabaseError(ApplicationError):
    """Raised when a database operation fails."""

    def __init__(self, message: str = "Database error") -> None:
        super().__init__(message, code="SYS_DATABASE_ERROR")
