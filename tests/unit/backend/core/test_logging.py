"""
Unit Tests for Centralized Logging.

Tests the logging configuration, structured fields, and source handling.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest


class TestValidSources:
    """Tests for VALID_SOURCES constant."""

    def test_valid_sources_contains_expected_values(self):
        """Should contain all recognized log source values."""
        from modules.backend.core.logging import VALID_SOURCES

        expected = frozenset({"web", "cli", "tui", "mobile", "telegram", "api", "tasks", "internal", "events"})
        assert VALID_SOURCES == expected

    def test_valid_sources_is_frozenset(self):
        """Should be a frozenset (immutable)."""
        from modules.backend.core.logging import VALID_SOURCES

        assert isinstance(VALID_SOURCES, frozenset)


class TestLoggingConfigLoading:
    """Tests for logging configuration loading from YAML."""

    def test_load_logging_config_reads_yaml_file(self):
        """Should load configuration from logging.yaml."""
        from modules.backend.core import logging as logging_module

        test_config = {
            "level": "DEBUG",
            "format": "console",
            "handlers": {
                "console": {"enabled": True},
                "file": {
                    "enabled": False,
                    "path": "logs/system.jsonl",
                    "max_bytes": 5242880,
                    "backup_count": 3,
                },
            },
        }

        logging_module._logging_config = None

        with patch("modules.backend.core.logging.load_yaml_config", return_value=test_config):
            config = logging_module._load_logging_config()

            assert config["level"] == "DEBUG"
            assert config["format"] == "console"
            assert config["handlers"]["console"]["enabled"] is True
            assert config["handlers"]["file"]["enabled"] is False
            assert config["handlers"]["file"]["path"] == "logs/system.jsonl"
            assert config["handlers"]["file"]["max_bytes"] == 5242880
            assert config["handlers"]["file"]["backup_count"] == 3

        logging_module._logging_config = None

    def test_load_logging_config_raises_if_file_missing(self):
        """Should raise FileNotFoundError if logging.yaml doesn't exist."""
        from modules.backend.core import logging as logging_module

        logging_module._logging_config = None

        with patch(
            "modules.backend.core.logging.load_yaml_config",
            side_effect=FileNotFoundError("Configuration file not found: logging.yaml"),
        ):
            with pytest.raises(FileNotFoundError) as exc_info:
                logging_module._load_logging_config()

            assert "logging.yaml" in str(exc_info.value)

        logging_module._logging_config = None

    def test_config_is_cached(self):
        """Should cache the configuration after first load."""
        from modules.backend.core import logging as logging_module

        test_config = {"level": "INFO", "format": "json"}

        logging_module._logging_config = None

        with patch("modules.backend.core.logging.load_yaml_config", return_value=test_config):
            config1 = logging_module._load_logging_config()
            config2 = logging_module._get_logging_config()

            assert config1 is config2

        logging_module._logging_config = None


class TestSetupLogging:
    """Tests for setup_logging function."""

    @pytest.fixture
    def mock_logging_config(self):
        """Create a mock logging configuration."""
        return {
            "level": "INFO",
            "format": "json",
            "handlers": {
                "console": {"enabled": True},
                "file": {
                    "enabled": True,
                    "path": "logs/system.jsonl",
                    "max_bytes": 10485760,
                    "backup_count": 5,
                },
            },
        }

    def test_setup_logging_configures_root_logger(self, tmp_path, mock_logging_config):
        """Should configure the root logger with correct level."""
        from modules.backend.core.logging import setup_logging

        with patch("modules.backend.core.logging._get_logging_config", return_value=mock_logging_config):
            setup_logging(level="DEBUG", format_type="json", enable_file_logging=False)

            root_logger = logging.getLogger()
            assert root_logger.level == logging.DEBUG

    def test_setup_logging_with_file_logging_disabled(self, mock_logging_config):
        """Should work without file logging."""
        from modules.backend.core.logging import setup_logging

        with patch("modules.backend.core.logging._get_logging_config", return_value=mock_logging_config):
            setup_logging(level="INFO", format_type="console", enable_file_logging=False)

            root_logger = logging.getLogger()
            handler_types = [type(h).__name__ for h in root_logger.handlers]
            assert "StreamHandler" in handler_types

    def test_setup_logging_with_file_logging_enabled(self, tmp_path, mock_logging_config):
        """Should create a single RotatingFileHandler for the JSONL file."""
        from modules.backend.core.logging import setup_logging

        log_file = tmp_path / "logs" / "system.jsonl"
        mock_logging_config["handlers"]["file"]["path"] = str(log_file)

        with patch("modules.backend.core.logging._get_logging_config", return_value=mock_logging_config), \
             patch("modules.backend.core.logging._resolve_log_path", return_value=log_file):
            setup_logging(level="INFO", format_type="json", enable_file_logging=True)

            root_logger = logging.getLogger()
            handler_types = [type(h).__name__ for h in root_logger.handlers]
            assert "RotatingFileHandler" in handler_types

    def test_setup_logging_uses_config_defaults(self, mock_logging_config):
        """Should use values from logging.yaml when not overridden."""
        from modules.backend.core.logging import setup_logging

        with patch("modules.backend.core.logging._get_logging_config", return_value=mock_logging_config):
            setup_logging(enable_file_logging=False)

            root_logger = logging.getLogger()
            assert root_logger.level == logging.INFO

    def test_setup_logging_override_takes_precedence(self, mock_logging_config):
        """Explicit parameters should override config values."""
        from modules.backend.core.logging import setup_logging

        with patch("modules.backend.core.logging._get_logging_config", return_value=mock_logging_config):
            setup_logging(level="DEBUG", enable_file_logging=False)

            root_logger = logging.getLogger()
            assert root_logger.level == logging.DEBUG


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_structlog_logger(self):
        """Should return a structlog logger."""
        from modules.backend.core.logging import get_logger

        logger = get_logger("test.module")
        assert hasattr(logger, "bind")
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")


class TestLogWithSource:
    """Tests for log_with_source helper function."""

    def test_log_with_source_adds_source_field(self):
        """Should add source field to log call."""
        from modules.backend.core.logging import get_logger, log_with_source

        logger = get_logger("test")
        mock_info = MagicMock()

        with patch.object(logger, "info", mock_info):
            log_with_source(logger, "tasks", "info", "Test message", extra_field="value")

            mock_info.assert_called_once_with(
                "Test message",
                source="tasks",
                extra_field="value",
            )

    def test_log_with_source_supports_different_levels(self):
        """Should support different log levels."""
        from modules.backend.core.logging import get_logger, log_with_source

        logger = get_logger("test")

        for level in ["debug", "info", "warning", "error", "critical"]:
            mock_method = MagicMock()
            with patch.object(logger, level, mock_method):
                log_with_source(logger, "web", level, f"Test {level}")
                mock_method.assert_called_once()

    def test_log_with_source_raises_on_invalid_level(self):
        """Should raise AttributeError for invalid log levels (no fallback)."""
        from modules.backend.core.logging import get_logger, log_with_source

        logger = get_logger("test")

        with pytest.raises(AttributeError):
            log_with_source(logger, "web", "nonexistent_level", "Test")


class TestResolveLogPath:
    """Tests for _resolve_log_path function."""

    def test_resolve_log_path_relative_to_project_root(self, tmp_path):
        """Should resolve path relative to project root."""
        from modules.backend.core.logging import _resolve_log_path

        with patch("modules.backend.core.logging.find_project_root", return_value=tmp_path):
            result = _resolve_log_path("logs/system.jsonl")
            assert result == tmp_path / "logs" / "system.jsonl"
