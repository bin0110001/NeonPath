"""Resolved AI configuration (pure data; secrets never leave this object)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AiConfig:
    enabled: bool
    provider: str
    model: str
    endpoint: str
    api_key: str = field(default="", repr=False)  # from the environment only; excluded from repr
    timeout_seconds: float = 30.0
    source: str = "environment"  # "environment" or "saved"
