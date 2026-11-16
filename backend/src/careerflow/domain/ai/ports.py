"""Provider-independent AI ports (plan section 19).

Domain and application code depend only on these types; provider SDKs live in
``infrastructure/llm`` and never leak their types here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class AiError(Exception):
    """Base class for every AI failure."""


class AiUnavailableError(AiError):
    """AI is disabled or not configured. Features report 'unavailable' instead of failing."""


class AiTimeoutError(AiError):
    pass


class AiRateLimitError(AiError):
    pass


class AiProviderError(AiError):
    """The provider failed (network, 5xx, auth...). The message must not contain secrets."""


class AiInvalidResponseError(AiError):
    """The model answered, but not with valid structured output. Never persist it as valid."""

    def __init__(self, message: str, *, raw_text: str, validation_errors: list[str]) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.validation_errors = validation_errors


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __add__(self, other: Usage) -> Usage:
        def add(a: int | None, b: int | None) -> int | None:
            return None if a is None and b is None else (a or 0) + (b or 0)

        return Usage(add(self.input_tokens, other.input_tokens), add(self.output_tokens, other.output_tokens))


@dataclass(frozen=True)
class CompletionRequest:
    system: str
    user: str
    prompt_key: str
    prompt_version: str
    json_output: bool = True
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class CompletionResult:
    text: str
    provider: str
    model: str
    usage: Usage = field(default_factory=Usage)


class LlmProvider(Protocol):
    """A text-completion backend. Implementations raise only ``AiError`` subclasses."""

    name: str
    model: str

    def complete(self, request: CompletionRequest) -> CompletionResult: ...
