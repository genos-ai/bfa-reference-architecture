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

from cli import cli
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
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "BFA Platform CLI" in result.output
        assert "--verbose" in result.output
        assert "--debug" in result.output
        assert "Commands:" in result.output

    def test_info_displays_app_info(self, runner):
        """Should display application info."""
        result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "BFF Python Web Application" in result.output
        assert "Commands" in result.output

    def test_verbose_flag_runs_successfully(self, runner):
        """Should run with --verbose without error."""
        result = runner.invoke(cli, ["--verbose", "info"])

        assert result.exit_code == 0
        assert "BFF Python Web Application" in result.output

    def test_debug_flag_runs_successfully(self, runner):
        """Should run with --debug without error."""
        result = runner.invoke(cli, ["--debug", "info"])

        assert result.exit_code == 0
        assert "BFF Python Web Application" in result.output

    def test_config_displays_configuration(self, runner):
        """Should display YAML configuration."""
        result = runner.invoke(cli, ["config"])

        assert result.exit_code == 0
        assert "Application Settings" in result.output
        assert "BFF Application" in result.output

    def test_health_runs_checks(self, runner):
        """Should run health checks."""
        result = runner.invoke(cli, ["health"])

        assert result.exit_code == 0
        assert "Health Check Results" in result.output
        assert "Core imports" in result.output

    def test_invalid_command_shows_error(self, runner):
        """Should show error for invalid command."""
        result = runner.invoke(cli, ["invalid"])

        assert result.exit_code != 0
        assert "No such command" in result.output


class TestSubcommandHelp:
    """Tests for subcommand help output — focused, scoped options."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    def test_server_help_shows_subcommands(self, runner):
        """Server help should show start/stop/status/restart subcommands."""
        result = runner.invoke(cli, ["server", "--help"])

        assert result.exit_code == 0
        assert "start" in result.output
        assert "stop" in result.output
        assert "status" in result.output
        assert "restart" in result.output
        assert "--objective" not in result.output
        assert "--table" not in result.output

    def test_mission_help_shows_subcommands(self, runner):
        """Mission help should list subcommands."""
        result = runner.invoke(cli, ["mission", "--help"])

        assert result.exit_code == 0
        assert "run" in result.output
        assert "list" in result.output
        assert "create" in result.output
        assert "detail" in result.output
        assert "cost" in result.output

    def test_mission_run_help_shows_options(self, runner):
        """Mission run help should show objective and budget options."""
        result = runner.invoke(cli, ["mission", "run", "--help"])

        assert result.exit_code == 0
        assert "OBJECTIVE" in result.output
        assert "--budget" in result.output
        assert "--roster" in result.output

    def test_playbook_help_shows_subcommands(self, runner):
        """Playbook help should list subcommands."""
        result = runner.invoke(cli, ["playbook", "--help"])

        assert result.exit_code == 0
        assert "run" in result.output
        assert "list" in result.output
        assert "detail" in result.output

    def test_db_help_shows_subcommands(self, runner):
        """DB help should list subcommands."""
        result = runner.invoke(cli, ["db", "--help"])

        assert result.exit_code == 0
        assert "stats" in result.output
        assert "query" in result.output
        assert "clear" in result.output

    def test_migrate_help_shows_subcommands(self, runner):
        """Migrate help should list subcommands."""
        result = runner.invoke(cli, ["migrate", "--help"])

        assert result.exit_code == 0
        assert "upgrade" in result.output
        assert "downgrade" in result.output
        assert "current" in result.output
        assert "autogenerate" in result.output

    def test_test_help_shows_type_choices(self, runner):
        """Test help should show type choices."""
        result = runner.invoke(cli, ["test", "--help"])

        assert result.exit_code == 0
        assert "unit" in result.output
        assert "integration" in result.output
        assert "--coverage" in result.output

    def test_credits_help_shows_roster_option(self, runner):
        """Credits help should show roster option."""
        result = runner.invoke(cli, ["credits", "--help"])

        assert result.exit_code == 0
        assert "--roster" in result.output


class TestCLIShortFlags:
    """Tests for short flag versions."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    def test_short_verbose_flag(self, runner):
        """Should accept -v for verbose."""
        result = runner.invoke(cli, ["-v", "info"])
        assert result.exit_code == 0

    def test_short_debug_flag(self, runner):
        """Should accept -d for debug."""
        result = runner.invoke(cli, ["-d", "info"])
        assert result.exit_code == 0


class TestActionBehavior:
    """Tests for specific action behaviors."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    def test_info_shows_examples(self, runner):
        """Should show usage examples in info output."""
        result = runner.invoke(cli, ["info"])

        assert "python cli.py" in result.output
        assert "Examples:" in result.output

    def test_config_shows_all_sections(self, runner):
        """Should show all configuration sections."""
        result = runner.invoke(cli, ["config"])

        assert "Application Settings" in result.output
        assert "Database Settings" in result.output
        assert "Logging Settings" in result.output
        assert "Feature Flags" in result.output

    def test_health_shows_pass_fail_status(self, runner):
        """Should show pass/fail status for each check."""
        result = runner.invoke(cli, ["health"])

        assert "PASS" in result.output or "FAIL" in result.output
        assert "Health Check" in result.output
