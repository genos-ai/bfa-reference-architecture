"""
Project Context Manager.

Reads, writes, and versions the Project Context Document (PCD).
Includes in-memory cache, size tracking, and seed PCD creation.
"""

import copy
import json as _json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.core.utils import estimate_tokens
from modules.backend.models.project_context import (
    ChangeType,
    ContextChange,
    ProjectContext,
)
from modules.backend.repositories.project_context import (
    ContextChangeRepository,
    ProjectContextRepository,
)
from modules.backend.services.base import BaseService

logger = get_logger(__name__)

# PCD size limits (bytes)
_PCD_MAX_SIZE = 20_480  # 20KB hard cap
_PCD_TARGET_SIZE = 15_360  # 15KB target

# In-memory cache: project_id -> (context_data, version, timestamp)
_cache: dict[str, tuple[dict, int, float]] = {}
_CACHE_TTL_SECONDS = 30.0

_SENTINEL = object()

# Restricted paths that agents cannot modify
_RESTRICTED_PATHS = {"version", "last_updated", "last_updated_by"}


def _get_nested(data: dict, path: str) -> Any:
    """Get a value from a nested dict using dot notation.

    Returns _SENTINEL if path not found.
    """
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list):
            if key == "-":
                return _SENTINEL
            try:
                current = current[int(key)]
            except (ValueError, IndexError):
                return _SENTINEL
        else:
            return _SENTINEL
    return current


def _set_nested(data: dict, path: str, value: Any) -> None:
    """Set a value in a nested dict using dot notation.

    Creates intermediate dicts as needed.
    """
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]

    final_key = keys[-1]
    if final_key == "-" and isinstance(current, list):
        current.append(value)
    else:
        current[final_key] = value


def _delete_nested(data: dict, path: str) -> Any:
    """Delete a value from a nested dict. Returns the old value."""
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None

    final_key = keys[-1]
    if isinstance(current, dict) and final_key in current:
        return current.pop(final_key)
    elif isinstance(current, list):
        try:
            idx = int(final_key)
            return current.pop(idx)
        except (ValueError, IndexError):
            return None
    return None


class ProjectContextManager(BaseService):
    """Service for PCD read/write with versioning, caching, and size tracking."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._context_repo = ProjectContextRepository(session)
        self._change_repo = ContextChangeRepository(session)

    @staticmethod
    @asynccontextmanager
    async def factory() -> AsyncGenerator["ProjectContextManager", None]:
        """Create a ProjectContextManager with its own DB session."""
        from modules.backend.core.database import get_async_session

        async with get_async_session() as db:
            yield ProjectContextManager(db)
            await db.commit()

    def _build_seed_pcd(self, project_name: str, description: str) -> dict:
        """Build the initial seed PCD for a new project."""
        return {
            "version": 1,
            "last_updated": "",
            "last_updated_by": "system:project_creation",
            "identity": {
                "name": project_name,
                "purpose": description,
                "tech_stack": [],
                "repo_structure": {},
            },
            "architecture": {
                "components": {},
                "data_flow": "",
                "conventions": {},
            },
            "decisions": [],
            "current_state": {
                "active_workstreams": [],
                "recent_milestones": [],
                "known_issues": [],
                "next_priorities": [],
            },
            "guardrails": [],
        }

    async def create_context(
        self,
        project_id: str,
        project_name: str,
        description: str,
    ) -> ProjectContext:
        """Create a seed PCD for a new project."""
        seed = self._build_seed_pcd(project_name, description)
        serialized = _json.dumps(seed, ensure_ascii=False)
        ctx = await self._context_repo.create(
            project_id=project_id,
            context_data=seed,
            version=1,
            size_characters=len(serialized),
            size_tokens=estimate_tokens(serialized),
        )
        _cache[project_id] = (seed, 1, time.monotonic())
        return ctx

    async def get_context(self, project_id: str) -> dict:
        """Get the PCD for a project. Uses in-memory cache with TTL.

        Always returns a deep copy so callers cannot corrupt
        the cache or the SQLAlchemy-tracked object.
        """
        cached = _cache.get(project_id)
        if cached:
            data, version, ts = cached
            if time.monotonic() - ts < _CACHE_TTL_SECONDS:
                return copy.deepcopy(data)

        ctx = await self._context_repo.get_by_project_id(project_id)
        if ctx is None:
            return {}

        data = copy.deepcopy(ctx.context_data)
        _cache[project_id] = (data, ctx.version, time.monotonic())
        return copy.deepcopy(data)

    async def get_context_with_version(
        self,
        project_id: str,
    ) -> tuple[dict, int]:
        """Get PCD content and version (for optimistic concurrency)."""
        ctx = await self._context_repo.get_by_project_id(project_id)
        if ctx is None:
            return {}, 0
        return ctx.context_data, ctx.version

    async def get_context_size(self, project_id: str) -> dict:
        """Get PCD size metrics."""
        ctx = await self._context_repo.get_by_project_id(project_id)
        if ctx is None:
            return {"size_characters": 0, "size_tokens": 0, "version": 0,
                    "pct_of_max": 0.0}
        return {
            "size_characters": ctx.size_characters,
            "size_tokens": ctx.size_tokens,
            "version": ctx.version,
            "pct_of_max": (ctx.size_characters / _PCD_MAX_SIZE) * 100,
        }

    async def apply_updates(
        self,
        project_id: str,
        updates: list[dict],
        *,
        agent_id: str | None = None,
        mission_id: str | None = None,
        task_id: str | None = None,
    ) -> tuple[int, list[str]]:
        """Apply context updates to the PCD.

        Returns (new_version, list_of_errors).
        Errors are logged and skipped — they do not fail the operation.
        Uses optimistic concurrency on the version field.
        """
        ctx = await self._context_repo.get_by_project_id(project_id)
        if ctx is None:
            return 0, ["ProjectContext not found for project"]

        current_version = ctx.version
        errors: list[str] = []
        data = copy.deepcopy(ctx.context_data)

        # Phase 1: Apply mutations to in-memory copy and collect valid changes.
        # Audit records are NOT written yet — we must check size first.
        applied_changes: list[dict] = []

        for update in updates:
            op = update.get("op")
            path = update.get("path", "")
            value = update.get("value")
            reason = update.get("reason", "no reason provided")

            # Validate restricted paths
            root_key = path.split(".")[0] if path else ""
            if root_key in _RESTRICTED_PATHS:
                errors.append(f"Restricted path: {path}")
                continue

            # Validate guardrails are append-only for agents
            if op == "remove" and path.startswith("guardrails") and agent_id:
                errors.append(f"Agents cannot remove guardrails: {path}")
                continue

            old_value = None
            change_type = None

            if op == "add":
                old_value = _get_nested(data, path)
                if old_value is _SENTINEL:
                    old_value = None
                _set_nested(data, path, value)
                change_type = ChangeType.ADD

            elif op == "replace":
                old_value = _get_nested(data, path)
                if old_value is _SENTINEL:
                    errors.append(f"Path not found for replace: {path}")
                    continue
                if old_value == value:
                    errors.append(f"No-op replace (value unchanged): {path}")
                    continue
                _set_nested(data, path, value)
                change_type = ChangeType.REPLACE

            elif op == "remove":
                old_value = _delete_nested(data, path)
                if old_value is None:
                    errors.append(f"Path not found for remove: {path}")
                    continue
                change_type = ChangeType.REMOVE

            else:
                errors.append(f"Unknown operation: {op}")
                continue

            applied_changes.append({
                "change_type": change_type,
                "path": path,
                "old_value": old_value if not isinstance(old_value, type(_SENTINEL)) else None,
                "new_value": value,
                "reason": reason,
            })

        # Update system fields
        data["version"] = current_version + 1
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        data["last_updated_by"] = agent_id or mission_id or "system"

        # Phase 2: Check size BEFORE writing any audit records.
        serialized = _json.dumps(data, ensure_ascii=False)
        new_size = len(serialized)
        if new_size > _PCD_MAX_SIZE:
            return current_version, [
                f"PCD would exceed size cap: {new_size} > {_PCD_MAX_SIZE} bytes. "
                "Prune before applying more updates."
            ]

        # Phase 3: Size check passed — write audit records.
        new_version = current_version + 1
        for change in applied_changes:
            await self._change_repo.create(
                context_id=ctx.id,
                version=new_version,
                change_type=change["change_type"],
                path=change["path"],
                old_value=change["old_value"],
                new_value=change["new_value"],
                agent_id=agent_id,
                mission_id=mission_id,
                task_id=task_id,
                reason=change["reason"],
            )

        # Phase 4: Optimistic concurrency write.
        rows_updated = await self._context_repo.update_context(
            project_id=project_id,
            context_data=data,
            new_version=new_version,
            size_characters=new_size,
            size_tokens=estimate_tokens(serialized),
        )

        if rows_updated == 0:
            return current_version, ["Version conflict — PCD was updated concurrently"]

        # Invalidate cache
        _cache.pop(project_id, None)

        self._log_operation(
            "PCD updated",
            project_id=project_id,
            new_version=new_version,
            size_characters=new_size,
            updates_applied=len(applied_changes),
            errors=len(errors),
        )

        return new_version, errors

    async def get_history(
        self,
        project_id: str,
        limit: int = 50,
    ) -> list[ContextChange]:
        """Get recent PCD change history."""
        ctx = await self._context_repo.get_by_project_id(project_id)
        if ctx is None:
            return []
        return await self._change_repo.list_by_context(ctx.id, limit=limit)
