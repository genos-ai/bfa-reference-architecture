#!/usr/bin/env python3
"""
List LLM Models — query provider APIs for available model names.

Reads API keys from config/.env and queries each configured provider's
API to retrieve available models.

Supported providers:
    - Anthropic (ANTHROPIC_API_KEY)
    - OpenAI (OPENAI_API_KEY)
    - Google Gemini (GEMINI_API_KEY)

Usage:
    python scripts/list_models.py
    python scripts/list_models.py --verbose
    python scripts/list_models.py --debug
    python scripts/list_models.py --provider anthropic
"""

import sys
from pathlib import Path
from typing import Any

import click
import httpx
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.core.config import find_project_root, get_app_config
from modules.backend.core.logging import get_logger, setup_logging

logger = get_logger(__name__)

PROVIDER_ENV_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def load_api_keys() -> dict[str, str]:
    """Load LLM provider API keys from config/.env.

    Returns:
        Dict mapping provider name to API key for each configured provider.

    Raises:
        FileNotFoundError: If config/.env does not exist.
    """
    env_path = find_project_root() / "config" / ".env"
    if not env_path.exists():
        raise FileNotFoundError(f"config/.env not found at {env_path}")

    env_values = dotenv_values(env_path)

    configured: dict[str, str] = {}
    for provider, env_key in PROVIDER_ENV_KEYS.items():
        value = env_values.get(env_key, "")
        if value:
            configured[provider] = value
            logger.debug("API key found", extra={"provider": provider})
        else:
            logger.debug("No API key configured", extra={"provider": provider})

    return configured


ModelEntry = tuple[str, str]
"""(model_id, display_name) — the ID is what you configure in an IDE or API call."""


def fetch_anthropic_models(api_key: str, client: httpx.Client) -> list[ModelEntry]:
    """Fetch available models from the Anthropic API.

    Handles pagination to retrieve all models.

    Args:
        api_key: Anthropic API key.
        client: HTTP client instance.

    Returns:
        Sorted list of (model_id, display_name) tuples.

    Raises:
        httpx.HTTPStatusError: If the API returns an error status.
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    models: list[ModelEntry] = []
    params: dict[str, Any] = {"limit": 100}

    while True:
        response = client.get(
            "https://api.anthropic.com/v1/models",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        models.extend(
            (m["id"], m.get("display_name", m["id"]))
            for m in data.get("data", [])
        )

        if not data.get("has_more", False):
            break
        last_id = data.get("last_id")
        if not last_id:
            break
        params["after_id"] = last_id

    return sorted(models, key=lambda e: e[0])


def fetch_openai_models(api_key: str, client: httpx.Client) -> list[ModelEntry]:
    """Fetch available models from the OpenAI API.

    Args:
        api_key: OpenAI API key.
        client: HTTP client instance.

    Returns:
        Sorted list of (model_id, display_name) tuples.
        OpenAI does not provide display names; the ID is used for both.

    Raises:
        httpx.HTTPStatusError: If the API returns an error status.
    """
    response = client.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    response.raise_for_status()
    data = response.json()
    return sorted(
        ((m["id"], m["id"]) for m in data.get("data", [])),
        key=lambda e: e[0],
    )


def fetch_gemini_models(api_key: str, client: httpx.Client) -> list[ModelEntry]:
    """Fetch available models from the Google Gemini API.

    Args:
        api_key: Google Gemini API key.
        client: HTTP client instance.

    Returns:
        Sorted list of (model_id, display_name) tuples.

    Raises:
        httpx.HTTPStatusError: If the API returns an error status.
    """
    models: list[ModelEntry] = []
    params: dict[str, Any] = {"key": api_key, "pageSize": 100}

    while True:
        response = client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        models.extend(
            (m["name"].removeprefix("models/"), m.get("displayName", m["name"]))
            for m in data.get("models", [])
        )

        next_token = data.get("nextPageToken")
        if not next_token:
            break
        params["pageToken"] = next_token

    return sorted(models, key=lambda e: e[0])


FETCH_FUNCTIONS: dict[str, Any] = {
    "anthropic": fetch_anthropic_models,
    "openai": fetch_openai_models,
    "gemini": fetch_gemini_models,
}


ProviderResult = list[ModelEntry] | str


def query_provider(
    provider: str, api_key: str, client: httpx.Client
) -> ProviderResult:
    """Query a single provider for its available models.

    Args:
        provider: Provider name (anthropic, openai, gemini).
        api_key: API key for the provider.
        client: HTTP client instance.

    Returns:
        Sorted list of ModelEntry tuples on success, or error string on failure.
    """
    fetch_fn = FETCH_FUNCTIONS.get(provider)
    if not fetch_fn:
        return f"Unsupported provider: {provider}"

    try:
        logger.info("Fetching models", extra={"provider": provider})
        models = fetch_fn(api_key, client)
        logger.info(
            "Models fetched", extra={"provider": provider, "count": len(models)}
        )
        return models
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}"
        try:
            body = e.response.json()
            detail = body.get("error", {}).get("message", str(body))
            error_msg = f"{error_msg}: {detail}"
        except Exception:
            pass
        logger.error("API error", extra={"provider": provider, "error": error_msg})
        return error_msg
    except httpx.RequestError as e:
        error_msg = f"Connection error: {e}"
        logger.error("Request failed", extra={"provider": provider, "error": str(e)})
        return error_msg


def display_results(results: dict[str, ProviderResult]) -> None:
    """Display model listing results grouped by provider.

    Args:
        results: Dict mapping provider name to model entries or error string.
    """
    for provider, models in results.items():
        click.echo()
        env_key = PROVIDER_ENV_KEYS[provider]
        click.secho(f"  {provider.upper()}  ({env_key})", fg="cyan", bold=True)
        click.echo(f"  {'─' * 70}")

        if isinstance(models, str):
            click.secho(f"  Error: {models}", fg="red")
        elif not models:
            click.secho("  No models returned", fg="yellow")
        else:
            id_width = max(len(mid) for mid, _ in models)
            click.secho(
                f"  {'#':>4}  {'Model ID':<{id_width}}  Display Name",
                bold=True,
            )
            click.echo(f"  {'─' * 70}")
            for i, (model_id, display_name) in enumerate(models, 1):
                click.echo(f"  {i:>4}  {model_id:<{id_width}}  {display_name}")
            click.echo(f"  {'─' * 70}")
            click.echo(f"  {len(models)} models available")


@click.command()
@click.option(
    "--verbose", "-v", is_flag=True, help="Enable verbose output (INFO level logging)."
)
@click.option(
    "--debug", "-d", is_flag=True, help="Enable debug output (DEBUG level logging)."
)
@click.option(
    "--provider",
    "-p",
    default=None,
    type=click.Choice(list(PROVIDER_ENV_KEYS.keys()), case_sensitive=False),
    help="Query only this provider (default: all configured).",
)
def main(verbose: bool, debug: bool, provider: str | None) -> None:
    """Query LLM provider APIs and list available model names."""
    if debug:
        setup_logging(level="DEBUG", format_type="console")
    elif verbose:
        setup_logging(level="INFO", format_type="console")
    else:
        setup_logging(level="WARNING", format_type="console")

    api_keys = load_api_keys()

    if not api_keys:
        click.secho("\nNo LLM provider API keys found in config/.env", fg="red")
        click.echo(f"Supported keys: {', '.join(PROVIDER_ENV_KEYS.values())}")
        sys.exit(1)

    if provider:
        if provider not in api_keys:
            click.secho(
                f"\nNo API key configured for {provider} "
                f"({PROVIDER_ENV_KEYS[provider]})",
                fg="red",
            )
            sys.exit(1)
        api_keys = {provider: api_keys[provider]}

    timeout = float(get_app_config().application.timeouts.external_api)
    click.echo()
    click.secho(
        f"  Querying {len(api_keys)} provider(s)...",
        fg="white",
        dim=True,
    )

    results: dict[str, ProviderResult] = {}
    with httpx.Client(timeout=timeout) as client:
        for name, key in api_keys.items():
            results[name] = query_provider(name, key, client)

    display_results(results)
    click.echo()


if __name__ == "__main__":
    main()
