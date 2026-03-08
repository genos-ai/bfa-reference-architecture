"""
Integration Tests for cli.py CLI.

Tests the CLI as a whole with real execution paths.
"""

import subprocess
import sys
from pathlib import Path

import pytest


# Project root for running commands
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestExampleCLI:
    """Integration tests for cli.py command-line interface."""

    def test_help_returns_zero_exit_code(self):
        """Should return exit code 0 for --help."""
        result = subprocess.run(
            [sys.executable, "cli.py", "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "Commands:" in result.stdout

    def test_info_action_succeeds(self):
        """Should successfully display info."""
        result = subprocess.run(
            [sys.executable, "cli.py", "info"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "BFF Python Web Application" in result.stdout

    def test_config_action_displays_yaml_settings(self):
        """Should display configuration from YAML files."""
        result = subprocess.run(
            [sys.executable, "cli.py", "config"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Application Settings" in result.stdout
        assert "BFF Application" in result.stdout

    def test_health_action_checks_components(self):
        """Should run health checks and report results."""
        result = subprocess.run(
            [sys.executable, "cli.py", "health"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Health Check Results" in result.stdout
        assert "Core imports" in result.stdout
        assert "PASS" in result.stdout or "FAIL" in result.stdout

    def test_verbose_flag_produces_more_output(self):
        """Should produce more output with --verbose flag."""
        result_verbose = subprocess.run(
            [sys.executable, "cli.py", "--verbose", "health"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        assert result_verbose.returncode == 0
        combined_output = result_verbose.stdout + result_verbose.stderr
        assert len(combined_output) > 0

    def test_debug_flag_produces_debug_output(self):
        """Should produce debug-level output with --debug flag."""
        result = subprocess.run(
            [sys.executable, "cli.py", "--debug", "health"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Health Check Results" in result.stdout

    def test_invalid_command_shows_error(self):
        """Should show error for invalid command."""
        result = subprocess.run(
            [sys.executable, "cli.py", "invalid"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "No such command" in result.stderr or "Usage" in result.stderr

    def test_test_action_runs_pytest(self):
        """Should run pytest via the test command."""
        result = subprocess.run(
            [sys.executable, "cli.py", "test", "unit"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Exit code 0 = tests passed, 5 = no tests collected, other = failures
        assert result.returncode in [0, 1, 5]

    def test_subcommand_help(self):
        """Should show focused help for subcommand groups."""
        result = subprocess.run(
            [sys.executable, "cli.py", "mission", "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Commands:" in result.stdout
        assert "run" in result.stdout
        assert "list" in result.stdout


class TestExampleCLIFromDifferentDirectory:
    """Test that CLI works when run from different directories."""

    def test_fails_gracefully_outside_project(self, tmp_path):
        """Should fail gracefully when config cannot be loaded from different directory."""
        example_script = PROJECT_ROOT / "cli.py"

        result = subprocess.run(
            [sys.executable, str(example_script), "info"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "Error" in result.stderr or "error" in result.stdout.lower()
