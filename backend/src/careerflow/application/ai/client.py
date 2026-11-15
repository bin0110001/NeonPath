"""Task-agnostic structured AI client: render prompt -> call provider -> validate.

Policy (plan section 19):
1. validate the model output against a Pydantic model,
2. on invalid output retry once with a repair instruction,
3. still invalid -> raise AiInvalidResponseError (raw text + errors preserved),
4. never return partially trusted data.
Timeouts and rate limits are retried with exponential backoff; other provider errors are not.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from careerflow.application.ai.prompts import PromptRegistry
from careerflow.domain.ai.ports import (
    AiInvalidResponseError,
    AiRateLimitError,
    AiTimeoutError,
    CompletionRequest,
    CompletionResult,
    LlmProvider,
    Usage,
)

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    """A validated answer plus the provenance every persisted result must keep."""

    value: T
    provider: str
    model: str
    prompt_key: str
    prompt_version: str
    usage: Usage
    attempts: int  # provider calls made (retries and the repair call included)


def _parse[T: BaseModel](text: str, model: type[T]) -> T:
    cleaned = text.strip()
    if match := _FENCE.match(cleaned):
        cleaned = match.group(1)
    return model.model_validate(json.loads(cleaned))


class AiClient:
    def __init__(
        self,
        provider: LlmProvider,
        registry: PromptRegistry | None = None,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.provider = provider
        self.registry = registry or PromptRegistry()
        self.retry = retry or RetryPolicy()
        self._sleep = sleep

    def run[T: BaseModel](
        self,
        prompt_key: str,
        variables: dict[str, str],
        response_model: type[T],
        version: str | None = None,
    ) -> StructuredResult[T]:
        prompt = self.registry.get(prompt_key, version)
        schema = json.dumps(response_model.model_json_schema())
        system, user = prompt.render({**variables, "schema": schema})
        usage = Usage()
        calls = 0

        result, spent, made = self._complete(system, user, prompt.key, prompt.version)
        usage, calls = usage + spent, calls + made
        try:
            value = _parse(result.text, response_model)
        except (ValueError, ValidationError) as first_error:
            repair = (
                f"{user}\n\nYour previous reply was not valid ({_describe(first_error)}). "
                "Reply again with ONLY a JSON object matching the schema, no commentary."
            )
            retry_result, spent, made = self._complete(system, repair, prompt.key, prompt.version)
            usage, calls = usage + spent, calls + made
            try:
                value = _parse(retry_result.text, response_model)
                result = retry_result
            except (ValueError, ValidationError) as second_error:
                raise AiInvalidResponseError(
                    f"model returned invalid output for {prompt.key}/{prompt.version}",
                    raw_text=retry_result.text,
                    validation_errors=[_describe(first_error), _describe(second_error)],
                ) from second_error
        return StructuredResult(
            value=value,
            provider=result.provider,
            model=result.model,
            prompt_key=prompt.key,
            prompt_version=prompt.version,
            usage=usage,
            attempts=calls,
        )

    def _complete(
        self, system: str, user: str, key: str, version: str
    ) -> tuple[CompletionResult, Usage, int]:
        request = CompletionRequest(
            system=system,
            user=user,
            prompt_key=key,
            prompt_version=version,
            timeout_seconds=self.retry.timeout_seconds,
        )
        for attempt in range(1, self.retry.max_attempts + 1):
            try:
                result = self.provider.complete(request)
            except (AiTimeoutError, AiRateLimitError):
                if attempt == self.retry.max_attempts:
                    raise
                self._sleep(self.retry.base_delay_seconds * 2 ** (attempt - 1))
            else:
                return result, result.usage, attempt
        raise AssertionError("unreachable")  # pragma: no cover


def _describe(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
    return f"{type(error).__name__}: {error}"
