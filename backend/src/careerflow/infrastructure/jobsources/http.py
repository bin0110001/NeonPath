"""Tiny HTTP port so adapters stay testable offline (tests inject recorded responses)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from careerflow.domain.sources.ports import SourceFetchError, SourceRateLimitedError

USER_AGENT = "CareerFlow/0.1 (+self-hosted job search tool)"


@dataclass(frozen=True)
class HttpResponse:
    status: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)


class HttpClient(Protocol):
    def get(self, url: str, *, headers: dict[str, str] | None = None, timeout: float = 15.0) -> HttpResponse: ...


class HttpxClient:
    """Real client: transport errors become SourceFetchError (never leaking headers/keys)."""

    def get(self, url: str, *, headers: dict[str, str] | None = None, timeout: float = 15.0) -> HttpResponse:
        try:
            response = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT, **(headers or {})},
                timeout=timeout,
                follow_redirects=True,
            )
        except httpx.TimeoutException as error:
            raise SourceFetchError(f"timed out after {timeout}s") from error
        except httpx.HTTPError as error:
            raise SourceFetchError(f"request failed: {type(error).__name__}") from error
        return HttpResponse(response.status_code, response.text, dict(response.headers))


def get_checked(
    client: HttpClient, url: str, *, headers: dict[str, str] | None = None, timeout: float = 15.0
) -> HttpResponse:
    """GET and translate HTTP status codes into the shared source error types."""
    response = client.get(url, headers=headers, timeout=timeout)
    if response.status == 429:
        retry_after = response.headers.get("Retry-After", "")
        raise SourceRateLimitedError(
            "source rate limit reached", retry_after_seconds=float(retry_after) if retry_after.isdigit() else None
        )
    if response.status >= 500:
        raise SourceFetchError(f"source returned HTTP {response.status}")
    if response.status >= 400:
        raise SourceFetchError(f"source returned HTTP {response.status}", retryable=False)
    return response
