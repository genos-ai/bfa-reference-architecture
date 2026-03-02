"""
Test configuration loader.

Reads test DB and related params from config/settings/test.yaml so test code
does not hardcode database URLs, hosts, or ports. See QA #22.
"""

from typing import Any

import yaml

from modules.backend.core.config import find_project_root


def load_test_config() -> dict[str, Any]:
    """Load config/settings/test.yaml. No hardcoded test params in code."""
    root = find_project_root()
    path = root / "config" / "settings" / "test.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Test config not found: {path}. Add config/settings/test.yaml for test DB params."
        )
    with open(path) as f:
        data = yaml.safe_load(f)
    return data or {}


def get_test_database_url() -> str:
    """
    Get the test database URL.

    Uses TEST_DATABASE_URL env if set, otherwise database_url from
    config/settings/test.yaml (no hardcoded fallbacks).
    """
    import os

    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    config = load_test_config()
    url = config.get("database_url")
    if not url:
        raise ValueError(
            "config/settings/test.yaml must define 'database_url' "
            "(or set TEST_DATABASE_URL env)"
        )
    return url


def get_test_database_config() -> dict[str, Any]:
    """
    Get test database section from config/settings/test.yaml.

    Used by unit/integration conftest for mock_app_config.database.
    """
    config = load_test_config()
    db = config.get("database")
    if not db:
        raise ValueError("config/settings/test.yaml must define 'database' section")
    return db


def get_test_redis_url() -> str:
    """
    Get the test Redis URL.

    Uses TEST_REDIS_URL env if set, otherwise redis_url from
    config/settings/test.yaml (no hardcoded fallbacks).
    """
    import os

    url = os.environ.get("TEST_REDIS_URL")
    if url:
        return url
    config = load_test_config()
    url = config.get("redis_url")
    if not url:
        raise ValueError(
            "config/settings/test.yaml must define 'redis_url' "
            "(or set TEST_REDIS_URL env)"
        )
    return url
