"""Providers that need no network: DisabledProvider and FixtureProvider."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from careerflow.domain.ai.ports import (
    AiError,
    AiUnavailableError,
    CompletionRequest,
    CompletionResult,
    Usage,
)


class DisabledProvider:
    """Used when AI is off: every call reports 'unavailable'."""

    name = "disabled"
    model = "none"

    def complete(self, request: CompletionRequest) -> CompletionResult:
        raise AiUnavailableError("AI is disabled (AI_ENABLED=false)")


Scripted = str | AiError | Callable[[CompletionRequest], str]


@dataclass
class Call:
    request: CompletionRequest


class FixtureProvider:
    """Deterministic provider for tests and demos.

    Responses are scripted per ``prompt_key`` as a queue of strings, exceptions to raise,
    or callables. The last scripted item for a key repeats, so a single response can serve
    many calls. Unscripted keys raise AiUnavailableError.
    """

    name = "fixture"

    def __init__(self, model: str = "fixture-1") -> None:
        self.model = model
        self._queues: dict[str, deque[Scripted]] = defaultdict(deque)
        self.calls: list[Call] = []

    def script(self, prompt_key: str, *responses: Scripted) -> FixtureProvider:
        self._queues[prompt_key].extend(responses)
        return self

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls.append(Call(request))
        queue = self._queues.get(request.prompt_key)
        if not queue:
            raise AiUnavailableError(f"no fixture scripted for {request.prompt_key}")
        item = queue[0] if len(queue) == 1 else queue.popleft()
        if isinstance(item, AiError):
            raise item
        text = item(request) if callable(item) else item
        words = len(request.user.split())
        return CompletionResult(
            text=text,
            provider=self.name,
            model=self.model,
            usage=Usage(input_tokens=words, output_tokens=len(text.split())),
        )
