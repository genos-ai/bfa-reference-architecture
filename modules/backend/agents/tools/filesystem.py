"""
Shared filesystem tool implementations.

Pure functions with no PydanticAI dependency. Each accepts explicit
parameters (project_root, file_path, scope) and enforces FileScope
before any I/O operation.
"""

from pathlib import Path

from modules.backend.agents.deps.base import FileScope


async def read_file(project_root: Path, file_path: str, scope: FileScope) -> str:
    """Read a file within the allowed scope. Returns content with line numbers.

    Args:
        project_root: Absolute path to the project root.
        file_path: Path relative to project root.
        scope: FileScope defining allowed read paths.

    Raises:
        PermissionError: If the path is not in the read scope.
    """
    scope.check_read(file_path)
    full_path = project_root / file_path

    if not full_path.is_file():
        return f"Error: file not found: {file_path}"

    lines = full_path.read_text(encoding="utf-8").splitlines()
    numbered = [f"{i:4d}| {line}" for i, line in enumerate(lines, 1)]
    return "\n".join(numbered)


async def list_files(
    project_root: Path,
    scope: FileScope,
    exclusion_paths: set[str] | None = None,
) -> list[str]:
    """List all Python files in scope, respecting exclusion patterns.

    Args:
        project_root: Absolute path to the project root.
        scope: FileScope defining allowed read paths.
        exclusion_paths: Set of path prefixes to exclude.

    Returns:
        Sorted list of relative paths to Python files within scope.
    """
    exclusions = exclusion_paths or set()
    files: list[str] = []

    for py_file in sorted(project_root.rglob("*.py")):
        rel = str(py_file.relative_to(project_root))
        if not scope.is_readable(rel):
            continue
        excluded = False
        for excl in exclusions:
            if rel.startswith(excl) or rel.startswith(excl.rstrip("/")):
                excluded = True
                break
        if not excluded:
            files.append(rel)

    return files
