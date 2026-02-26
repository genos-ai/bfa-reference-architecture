"""
Shared code tool implementations.

Pure functions for code modification and testing. Each enforces FileScope
before any write operation. No PydanticAI dependency.
"""

import subprocess
import sys
from pathlib import Path

from modules.backend.agents.deps.base import FileScope


async def apply_fix(
    project_root: Path,
    file_path: str,
    old_text: str,
    new_text: str,
    scope: FileScope,
) -> dict:
    """Replace exact text in a file within the allowed scope.

    The old_text must appear exactly once in the file.

    Args:
        project_root: Absolute path to the project root.
        file_path: Path relative to project root.
        old_text: Exact text to find (must appear exactly once).
        new_text: Replacement text.
        scope: FileScope defining allowed write paths.

    Returns:
        Dict with success status and file path or error message.
    """
    scope.check_write(file_path)
    full_path = project_root / file_path

    if not full_path.is_file():
        return {"success": False, "error": f"File not found: {file_path}"}

    content = full_path.read_text(encoding="utf-8")
    count = content.count(old_text)

    if count == 0:
        return {"success": False, "error": "old_text not found in file"}
    if count > 1:
        return {"success": False, "error": f"old_text found {count} times — must be unique"}

    new_content = content.replace(old_text, new_text, 1)
    full_path.write_text(new_content, encoding="utf-8")

    return {"success": True, "file": file_path}


async def run_tests(project_root: Path) -> dict:
    """Run the unit test suite and return results.

    Returns:
        Dict with passed (bool), exit_code (int), and output (str tail).
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit", "-v", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    output_lines = result.stdout.splitlines()
    tail = "\n".join(output_lines[-50:]) if len(output_lines) > 50 else result.stdout
    passed = result.returncode == 0

    return {
        "passed": passed,
        "exit_code": result.returncode,
        "output": tail,
    }
