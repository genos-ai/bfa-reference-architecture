"""
Unit Tests for cli.py Entry Script.

Tests real functions against real configuration.
"""

import os
import pytest
from pathlib import Path
from click.testing import CliRunner

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cli import main
from modules.backend.core.config import validate_project_root


class TestValidateProjectRoot:
    """Tests for validate_project_root function."""

    def test_validate_project_root_succeeds_when_marker_exists(self, tmp_path):
        """Should return path when .project_root exists."""
        marker = tmp_path / ".project_root"
        marker.touch()

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = validate_project_root()
            assert result == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_validate_project_root_exits_when_marker_missing(self, tmp_path):
        """Should raise SystemExit when .project_root is not found."""
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(SystemExit):
                validate_project_root()
        finally:
            os.chdir(original_cwd)


class TestMainCLI:
    """Tests for main CLI entry point."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    def test_help_displays_usage(self, runner):
        """Should display help text with --help."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "BFA Platform CLI" in result.output
        assert "--service" in result.output
        assert "--verbose" in result.output
        assert "--debug" in result.output

    def test_info_action_displays_app_info(self, runner):
        """Should display application info with --service info."""
        result = runner.invoke(main, ["--service", "info"])

        assert result.exit_code == 0
        assert "BFF Python Web Application" in result.output
        assert "Services (--service):" in result.output

    def test_verbose_flag_runs_successfully(self, runner):
        """Should run with --verbose without error."""
        result = runner.invoke(main, ["--service", "info", "--verbose"])

        assert result.exit_code == 0
        assert "BFF Python Web Application" in result.output

    def test_debug_flag_runs_successfully(self, runner):
        """Should run with --debug without error."""
        result = runner.invoke(main, ["--service", "info", "--debug"])

        assert result.exit_code == 0
        assert "BFF Python Web Application" in result.output

    def test_config_action_displays_configuration(self, runner):
        """Should display YAML configuration with --action config."""
        # Act - use real config since it's available
        result = runner.invoke(main, ["--service", "config"])

        # Assert
        assert result.exit_code == 0
        assert "Application Settings" in result.output
        assert "BFF Application" in result.output

    def test_health_action_runs_checks(self, runner):
        """Should run health checks with --action health."""
        # Act
        result = runner.invoke(main, ["--service", "health"])

        # Assert
        assert result.exit_code == 0
        assert "Health Check Results" in result.output
        assert "Core imports" in result.output

    def test_invalid_action_shows_error(self, runner):
        """Should show error for invalid action value."""
        # Act
        result = runner.invoke(main, ["--service", "invalid"])

        # Assert
        assert result.exit_code != 0
        assert "Invalid value" in result.output


class TestCLIOptions:
    """Tests for CLI option combinations."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    def test_server_options_are_available(self, runner):
        """Should accept server-related options."""
        # Act
        result = runner.invoke(main, ["--help"])

        # Assert
        assert "--host" in result.output
        assert "--port" in result.output
        assert "--reload" in result.output

    def test_test_options_are_available(self, runner):
        """Should accept test-related options."""
        # Act
        result = runner.invoke(main, ["--help"])

        # Assert
        assert "--test-type" in result.output
        assert "--coverage" in result.output

    def test_short_flags_work(self, runner):
        """Should accept short flag versions."""
        # Act - use -v for verbose
        result = runner.invoke(main, ["-v", "--service", "info"])

        # Assert
        assert result.exit_code == 0

        # Act - use -d for debug
        result = runner.invoke(main, ["-d", "--service", "info"])

        # Assert
        assert result.exit_code == 0


class TestActionBehavior:
    """Tests for specific action behaviors."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    def test_info_shows_examples(self, runner):
        """Should show usage examples in info output."""
        # Act
        result = runner.invoke(main, ["--service", "info"])

        # Assert
        assert "python cli.py" in result.output
        assert "Examples:" in result.output

    def test_config_shows_all_sections(self, runner):
        """Should show all configuration sections."""
        # Act
        result = runner.invoke(main, ["--service", "config"])

        # Assert
        assert "Application Settings" in result.output
        assert "Database Settings" in result.output
        assert "Logging Settings" in result.output
        assert "Feature Flags" in result.output

    def test_health_shows_pass_fail_status(self, runner):
        """Should show pass/fail status for each check."""
        # Act
        result = runner.invoke(main, ["--service", "health"])

        # Assert
        # Should have either PASS or FAIL indicators
        assert "PASS" in result.output or "FAIL" in result.output
        assert "---" in result.output  # Separator line
