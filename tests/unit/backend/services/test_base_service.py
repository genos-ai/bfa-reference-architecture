"""
Unit Tests for Base Service.

Tests the BaseService class methods and error handling.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from modules.backend.services.base import BaseService
from modules.backend.core.exceptions import (
    ConflictError,
    DatabaseError,
    ValidationError,
)


class TestBaseServiceInit:
    """Tests for BaseService initialization."""

    def test_init_stores_session(self):
        """Should store the provided session."""
        mock_session = AsyncMock()

        service = BaseService(mock_session)

        assert service._session is mock_session
        assert service.session is mock_session

    def test_init_creates_logger(self):
        """Should create a logger for the service."""
        mock_session = AsyncMock()

        service = BaseService(mock_session)

        assert service._logger is not None


class TestExecuteDbOperation:
    """Tests for _execute_db_operation method."""

    @pytest.fixture
    def service(self):
        """Create a BaseService instance."""
        return BaseService(AsyncMock())

    @pytest.mark.asyncio
    async def test_returns_result_on_success(self, service):
        """Should return the coroutine result on success."""
        async def successful_operation():
            return {"id": "123", "name": "test"}

        result = await service._execute_db_operation(
            "test_operation",
            successful_operation(),
        )

        assert result == {"id": "123", "name": "test"}

    @pytest.mark.asyncio
    async def test_raises_conflict_on_unique_violation(self, service):
        """Should raise ConflictError on unique constraint violation."""
        async def failing_operation():
            raise IntegrityError(
                "statement",
                {},
                Exception("UNIQUE constraint failed"),
            )

        with pytest.raises(ConflictError) as exc_info:
            await service._execute_db_operation(
                "create_user",
                failing_operation(),
            )

        assert "already exists" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_raises_conflict_on_duplicate_key(self, service):
        """Should raise ConflictError on PostgreSQL unique violation (pgcode 23505)."""
        pg_orig = Exception("duplicate key value violates unique constraint")
        pg_orig.pgcode = "23505"

        async def failing_operation():
            raise IntegrityError(
                "statement",
                {},
                pg_orig,
            )

        with pytest.raises(ConflictError):
            await service._execute_db_operation(
                "create_item",
                failing_operation(),
            )

    @pytest.mark.asyncio
    async def test_raises_database_error_on_other_integrity_error(self, service):
        """Should raise DatabaseError on non-unique integrity errors."""
        async def failing_operation():
            raise IntegrityError(
                "statement",
                {},
                Exception("foreign key constraint"),
            )

        with pytest.raises(DatabaseError) as exc_info:
            await service._execute_db_operation(
                "update_item",
                failing_operation(),
            )

        assert "constraint violation" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_raises_database_error_on_sqlalchemy_error(self, service):
        """Should raise DatabaseError on general SQLAlchemy errors."""
        async def failing_operation():
            raise SQLAlchemyError("Connection lost")

        with pytest.raises(DatabaseError) as exc_info:
            await service._execute_db_operation(
                "fetch_data",
                failing_operation(),
            )

        assert "operation failed" in str(exc_info.value.message)


class TestValidateRequired:
    """Tests for _validate_required method."""

    @pytest.fixture
    def service(self):
        """Create a BaseService instance."""
        return BaseService(AsyncMock())

    def test_passes_when_all_fields_present(self, service):
        """Should not raise when all required fields are present."""
        fields = {"name": "John", "email": "john@example.com"}

        # Should not raise
        service._validate_required(fields, ["name", "email"])

    def test_raises_when_field_missing(self, service):
        """Should raise ValidationError when field is missing."""
        fields = {"name": "John"}

        with pytest.raises(ValidationError) as exc_info:
            service._validate_required(fields, ["name", "email"])

        assert "email" in exc_info.value.details["missing_fields"]

    def test_raises_when_field_is_none(self, service):
        """Should raise ValidationError when field is None."""
        fields = {"name": "John", "email": None}

        with pytest.raises(ValidationError) as exc_info:
            service._validate_required(fields, ["name", "email"])

        assert "email" in exc_info.value.details["missing_fields"]

    def test_raises_when_string_field_is_empty(self, service):
        """Should raise ValidationError when string field is empty."""
        fields = {"name": "John", "email": "   "}

        with pytest.raises(ValidationError) as exc_info:
            service._validate_required(fields, ["name", "email"])

        assert "email" in exc_info.value.details["missing_fields"]

    def test_reports_all_missing_fields(self, service):
        """Should report all missing fields, not just the first."""
        fields = {"other": "value"}

        with pytest.raises(ValidationError) as exc_info:
            service._validate_required(fields, ["name", "email", "phone"])

        missing = exc_info.value.details["missing_fields"]
        assert "name" in missing
        assert "email" in missing
        assert "phone" in missing


class TestValidateStringLength:
    """Tests for _validate_string_length method."""

    @pytest.fixture
    def service(self):
        """Create a BaseService instance."""
        return BaseService(AsyncMock())

    def test_passes_when_length_in_bounds(self, service):
        """Should not raise when string length is within bounds."""
        # Should not raise
        service._validate_string_length("hello", "name", min_length=3, max_length=10)

    def test_raises_when_too_short(self, service):
        """Should raise ValidationError when string is too short."""
        with pytest.raises(ValidationError) as exc_info:
            service._validate_string_length("ab", "password", min_length=8)

        assert "too short" in exc_info.value.message
        assert "password" in exc_info.value.details

    def test_raises_when_too_long(self, service):
        """Should raise ValidationError when string is too long."""
        with pytest.raises(ValidationError) as exc_info:
            service._validate_string_length("a" * 300, "name", max_length=255)

        assert "too long" in exc_info.value.message
        assert "name" in exc_info.value.details

    def test_allows_no_min_constraint(self, service):
        """Should allow omitting min_length constraint."""
        # Should not raise for empty string when no min
        service._validate_string_length("", "optional_field", max_length=100)

    def test_allows_no_max_constraint(self, service):
        """Should allow omitting max_length constraint."""
        # Should not raise for long string when no max
        service._validate_string_length("a" * 10000, "description", min_length=1)


class TestLoggingMethods:
    """Tests for logging helper methods."""

    @pytest.fixture
    def service(self):
        """Create a BaseService instance."""
        return BaseService(AsyncMock())

    def test_log_operation_includes_service_name(self, service):
        """Should include service class name in log context."""
        with patch.object(service._logger, "info") as mock_info:
            service._log_operation("Creating user", user_id="123")

            mock_info.assert_called_once()
            call_kwargs = mock_info.call_args
            extra = call_kwargs[1]["extra"]
            assert extra["service"] == "BaseService"
            assert extra["user_id"] == "123"

    def test_log_debug_includes_service_name(self, service):
        """Should include service class name in debug log context."""
        with patch.object(service._logger, "debug") as mock_debug:
            service._log_debug("Processing step", step=1)

            mock_debug.assert_called_once()
            call_kwargs = mock_debug.call_args
            extra = call_kwargs[1]["extra"]
            assert extra["service"] == "BaseService"
            assert extra["step"] == 1


class TestServiceInheritance:
    """Tests for service inheritance patterns."""

    def test_subclass_can_access_session(self):
        """Subclass should be able to access the session."""
        class MyService(BaseService):
            def get_session(self):
                return self.session

        mock_session = AsyncMock()
        service = MyService(mock_session)

        assert service.get_session() is mock_session

    def test_subclass_inherits_validation_methods(self):
        """Subclass should inherit validation methods."""
        class MyService(BaseService):
            def validate_user(self, data: dict):
                self._validate_required(data, ["email"])
                self._validate_string_length(
                    data["email"], "email", min_length=5, max_length=255
                )

        service = MyService(AsyncMock())

        # Should not raise for valid data
        service.validate_user({"email": "test@example.com"})

        # Should raise for invalid data
        with pytest.raises(ValidationError):
            service.validate_user({"email": "ab"})
