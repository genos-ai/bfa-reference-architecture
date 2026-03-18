"""
CLI handler for --service test.

Runs the pytest test suite with optional coverage.
"""

import subprocess
import sys

import click


def run_tests(logger, test_type: str, coverage: bool) -> None:
    """Run the test suite."""
    logger.info("Running tests", extra={"type": test_type, "coverage": coverage})

    cmd = [sys.executable, "-m", "pytest"]

    if test_type == "unit":
        cmd.append("tests/unit")
    elif test_type == "integration":
        cmd.append("tests/integration")
    elif test_type == "e2e":
        cmd.append("tests/e2e")
    else:
        cmd.append("tests/")

    cmd.append("-v")

    if coverage:
        cmd.extend(["--cov=modules/backend", "--cov-report=term-missing"])

    click.echo(f"Running: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except FileNotFoundError:
        logger.error("pytest not found. Install with: pip install pytest")
        sys.exit(1)
