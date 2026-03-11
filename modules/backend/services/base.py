"""
Base Service.

Base class for all services providing common patterns for business logic.
Services orchestrate repositories, handle transactions, and implement
business rules.

Usage:
    from modules.backend.services.base import BaseService

    class UserService(BaseService):
        def __init__(self, session: AsyncSession) -> None:
            super().__init__(session)
            self.user_repo = UserRepository(session)

        async def create_user(self, email: str, password: str) -> User:
            # Validation
            if await self.user_repo.exists_by_email(email):
                raise ConflictError("Email already registered")

            # Business logic
            hashed = hash_password(password)
            return await self.user_repo.create(email=email, hashed_password=hashed)
"""

from typing import Any, TypeVar

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.exceptions import (
    ConflictError,
    DatabaseError,
    ValidationError,
)
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class BaseService:
    """
    Base class for all services.

    Provides:
    - Database session management
    - Logging context
    - Error wrapping for database operations
    - Common validation patterns

    Subclasses should:
    - Call super().__init__(session) in their __init__
    - Initialize repositories in __init__
    - Implement business logic methods
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize the service with a database session.

        Args:
            session: SQLAlchemy async session for database operations
        """
        self._session = session
        self._logger = get_logger(self.__class__.__module__)

    @property
    def session(self) -> AsyncSession:
        """Get the database session."""
        return self._session

    async def _execute_db_operation(
        self,
        operation: str,
        coro: Any,
    ) -> T:
        """
        Execute a database operation with error handling.

        Wraps database operations to convert SQLAlchemy exceptions
        to application-specific exceptions.

        Args:
            operation: Description of the operation for logging
            coro: Coroutine to execute

        Returns:
            Result of the coroutine

        Raises:
            ConflictError: For unique constraint violations
            DatabaseError: For other database errors
        """
        try:
            return await coro
        except IntegrityError as e:
            self._logger.warning(
                "Database integrity error",
                extra={"operation": operation, "error": str(e)},
            )
            # Check for unique constraint violation via DB driver
            orig = e.orig
            is_unique = (
                # psycopg / psycopg2: UniqueViolation (SQLSTATE 23505)
                getattr(orig, "pgcode", None) == "23505"
                # SQLite: UNIQUE constraint failed
                or (
                    hasattr(orig, "args")
                    and orig.args
                    and "UNIQUE constraint failed" in str(orig.args[0])
                )
            )
            if is_unique:
                raise ConflictError("Resource already exists")
            raise DatabaseError(f"Database constraint violation: {operation}")
        except SQLAlchemyError as e:
            self._logger.error(
                "Database error",
                extra={"operation": operation, "error": str(e)},
            )
            raise DatabaseError(f"Database operation failed: {operation}")

    def _validate_required(
        self,
        fields: dict[str, Any],
        field_names: list[str],
    ) -> None:
        """
        Validate that required fields are present and not empty.

        Args:
            fields: Dictionary of field names to values
            field_names: List of required field names

        Raises:
            ValidationError: If any required field is missing or empty
        """
        missing = []
        for name in field_names:
            value = fields.get(name)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(name)

        if missing:
            raise ValidationError(
                "Required fields missing",
                details={"missing_fields": missing},
            )

    def _validate_string_length(
        self,
        value: str,
        field_name: str,
        min_length: int | None = None,
        max_length: int | None = None,
    ) -> None:
        """
        Validate string length constraints.

        Args:
            value: String value to validate
            field_name: Name of the field for error messages
            min_length: Minimum allowed length (optional)
            max_length: Maximum allowed length (optional)

        Raises:
            ValidationError: If string length is out of bounds
        """
        if min_length is not None and len(value) < min_length:
            raise ValidationError(
                f"{field_name} too short",
                details={field_name: f"Minimum length is {min_length}"},
            )
        if max_length is not None and len(value) > max_length:
            raise ValidationError(
                f"{field_name} too long",
                details={field_name: f"Maximum length is {max_length}"},
            )

    def _log_operation(
        self,
        operation: str,
        **context: Any,
    ) -> None:
        """
        Log a service operation with context.

        Args:
            operation: Description of the operation
            **context: Additional context to include in log
        """
        self._logger.info(
            operation,
            extra={"service": self.__class__.__name__, **context},
        )

    def _log_debug(
        self,
        message: str,
        **context: Any,
    ) -> None:
        """
        Log debug information.

        Args:
            message: Debug message
            **context: Additional context to include in log
        """
        self._logger.debug(
            message,
            extra={"service": self.__class__.__name__, **context},
        )
