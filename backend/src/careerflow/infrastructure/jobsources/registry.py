"""Source registry. Add an adapter by registering a factory here: no evaluation or
workflow code changes are needed (ADR-006)."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from careerflow.domain.sources.ports import JobSourceAdapter, SourceConfigError
from careerflow.infrastructure.jobsources.http import HttpClient, HttpxClient
from careerflow.infrastructure.jobsources.simple import FixtureJobAdapter, ManualJobAdapter

AdapterFactory = Callable[[dict[str, Any], HttpClient], JobSourceAdapter]

ADAPTERS: dict[str, AdapterFactory] = {
    "manual": lambda config, http: ManualJobAdapter(config),
    "fixture": lambda config, http: FixtureJobAdapter(config),
}

SECRET_KEYS = ("api_key", "apikey", "token", "secret", "password", "authorization")


def register(name: str, factory: AdapterFactory) -> None:
    ADAPTERS[name] = factory


def resolve_env_secrets(config: dict[str, Any]) -> dict[str, Any]:
    """``{"api_key_env": "MY_VAR"}`` becomes ``{"api_key": <value of MY_VAR>}`` at runtime,
    so secrets are never stored in the database."""
    resolved = dict(config)
    for key, value in config.items():
        if key.endswith("_env") and isinstance(value, str):
            secret = os.environ.get(value)
            if not secret:
                raise SourceConfigError(f"environment variable {value} (for {key[:-4]}) is not set")
            resolved[key[:-4]] = secret
    return resolved


def build_adapter(
    adapter: str, config: dict[str, Any], http: HttpClient | None = None
) -> JobSourceAdapter:
    try:
        factory = ADAPTERS[adapter]
    except KeyError:
        raise SourceConfigError(f"unknown adapter {adapter!r}; known: {sorted(ADAPTERS)}") from None
    return factory(resolve_env_secrets(config), http or HttpxClient())


def mask_config(config: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``config`` that is safe to return from the API or log."""
    return {
        key: (
            "***"
            if any(s in key.lower() for s in SECRET_KEYS) and not key.endswith("_env") and value
            else value  # "<name>_env" holds only an environment variable *name*
        )
        for key, value in config.items()
    }
