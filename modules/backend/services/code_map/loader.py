"""Code Map loader — load, cache, and refresh Code Map artifacts.

Reusable service for loading Code Map JSON and Markdown from disk,
checking staleness against git HEAD, and regenerating when stale.

Used by:
    - Planning Agent integration (Plan 20) — JSON for structural awareness
    - Context Assembler (Plan 20) — Markdown for coding agent context
    - Quality Agent (Plan 19) — JSON for dependency analysis
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

# Default file locations relative to project root
_JSON_PATH = Path(".codemap") / "map.json"
_MARKDOWN_PATH = Path("CODEMAP.md")


class CodeMapLoader:
    """Load, cache, and refresh Code Map artifacts.

    Designed for single-instance reuse within a process. Caches the
    loaded JSON in memory so multiple consumers (planning, context
    assembly, quality) don't re-read the same file.

    Usage::

        loader = CodeMapLoader(project_root)
        code_map = loader.get_json()          # dict or None
        markdown = loader.get_markdown()      # str or None
        loader.ensure_fresh()                 # regenerate if stale
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._json_path = project_root / _JSON_PATH
        self._md_path = project_root / _MARKDOWN_PATH
        self._cached_json: dict | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_json(self, *, force_reload: bool = False) -> dict | None:
        """Load the Code Map JSON, returning cached copy if available."""
        if self._cached_json is not None and not force_reload:
            return self._cached_json

        if not self._json_path.exists():
            logger.warning("Code Map JSON not found at %s", self._json_path)
            return None

        try:
            data = json.loads(self._json_path.read_text(encoding="utf-8"))
            self._cached_json = data
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load Code Map JSON: %s", exc)
            return None

    def get_markdown(self) -> str | None:
        """Load the pre-rendered Code Map Markdown."""
        if not self._md_path.exists():
            logger.warning("Code Map Markdown not found at %s", self._md_path)
            return None

        try:
            return self._md_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to load Code Map Markdown: %s", exc)
            return None

    def is_stale(self) -> bool:
        """Check if the Code Map commit hash differs from git HEAD."""
        code_map = self.get_json()
        if code_map is None:
            return True

        map_commit = code_map.get("commit", "")
        if not map_commit:
            return True

        head_commit = self._git_head()
        if not head_commit:
            return False  # Can't determine — assume fresh

        return map_commit != head_commit

    def ensure_fresh(self) -> dict | None:
        """Load the Code Map, regenerating if stale or missing.

        Returns the (possibly regenerated) JSON dict, or None on failure.
        """
        code_map = self.get_json()

        if code_map is None or self.is_stale():
            logger.info("Code Map is stale or missing — regenerating")
            code_map = self.regenerate()

        return code_map

    def regenerate(self) -> dict | None:
        """Regenerate both JSON and Markdown from the current codebase."""
        from modules.backend.services.code_map.generator import generate_code_map
        from modules.backend.services.code_map.assembler import render_markdown_tree

        try:
            code_map = generate_code_map(
                repo_root=self._root,
                scope=["modules/"],
                project_id=self._root.name,
            )

            # Write JSON
            self._json_path.parent.mkdir(parents=True, exist_ok=True)
            self._json_path.write_text(
                json.dumps(code_map, indent=2), encoding="utf-8",
            )

            # Write Markdown
            markdown = render_markdown_tree(code_map)
            self._md_path.write_text(markdown, encoding="utf-8")

            # Update cache
            self._cached_json = code_map

            stats = code_map.get("stats", {})
            logger.info(
                "Code Map regenerated (%d files, %d lines)",
                stats.get("total_files", 0),
                stats.get("total_lines", 0),
            )
            return code_map

        except Exception as exc:
            logger.warning("Failed to regenerate Code Map: %s", exc)
            return None

    def invalidate_cache(self) -> None:
        """Clear the in-memory cache, forcing next get_json() to re-read."""
        self._cached_json = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _git_head(self) -> str:
        """Get the current HEAD commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""
