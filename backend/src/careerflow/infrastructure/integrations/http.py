"""HTTP port for integrations (any method, JSON or form bodies)."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from careerflow.domain.integrations.ports import IntegrationError
from careerflow.infrastructure.jobsources.http import HttpResponse

USER_AGENT = "CareerFlow/0.1"


class IntegrationHttp(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> HttpResponse: ...


class HttpxIntegrationClient:
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> HttpResponse:
        try:
            response = httpx.request(
                method, url, headers={"User-Agent": USER_AGENT, **(headers or {})},
                params=params, json=json, data=data, timeout=timeout,
            )  # fmt: skip
        except httpx.TimeoutException as error:
            raise IntegrationError(f"request timed out after {timeout}s") from error
        except httpx.HTTPError as error:
            # never include the request (it carries credentials) in the message
            raise IntegrationError(f"request failed ({type(error).__name__})") from error
        return HttpResponse(response.status_code, response.text, dict(response.headers))
