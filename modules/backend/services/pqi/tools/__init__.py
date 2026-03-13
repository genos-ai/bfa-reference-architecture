"""External tool integrations for PQI scoring.

Each tool module follows the same contract:
    is_available() -> bool           Check if the tool is installed
    run(repo_root, scope, exclude)   Run the tool and return parsed results

The discovery layer auto-detects which tools are installed and runs
only those that are available. Dimensions gracefully degrade when
a tool is missing — AST-based scoring fills the gap at lower confidence.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Finding:
    """A single finding from an external tool."""

    rule_id: str
    severity: str
    confidence: str
    message: str
    file: str
    line: int
    tool: str


@dataclass
class ToolResult:
    """Parsed output from an external tool run."""

    tool: str
    available: bool
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    raw_output: str = ""
    error: str = ""

    @property
    def success(self) -> bool:
        return self.available and not self.error


def check_installed(command: str) -> bool:
    """Check if a CLI tool is installed and on PATH."""
    return shutil.which(command) is not None


def run_command(
    args: list[str],
    cwd: Path,
    timeout: int = 120,
) -> tuple[str, str, int]:
    """Run a CLI command and return (stdout, stderr, returncode).

    Does not raise on non-zero exit — many tools use non-zero
    to indicate findings were found (not errors).
    """
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s", -1
    except OSError as e:
        return "", str(e), -1
