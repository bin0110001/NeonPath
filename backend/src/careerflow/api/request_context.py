"""Request-id middleware: binds log context per request and logs one access line."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from careerflow.infrastructure.logging import bind_log_context, log_context

logger = logging.getLogger("careerflow.request")

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_UUID = r"[0-9a-fA-F-]{36}"
_JOB_PATH = re.compile(rf"/jobs/({_UUID})")
_PROFILE_PATH = re.compile(rf"/profiles/({_UUID})")


def _request_id(request: Request) -> str:
    supplied = request.headers.get(REQUEST_ID_HEADER, "")
    # Only accept well-formed ids so callers cannot inject newlines/JSON into logs.
    return supplied if _SAFE_REQUEST_ID.match(supplied) else uuid.uuid4().hex


def install_request_context(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _request_id(request)
        path = request.url.path
        job = _JOB_PATH.search(path)
        profile = _PROFILE_PATH.search(path)
        with log_context(request_id=request_id):
            bind_log_context(
                job_id=job.group(1) if job else None,
                profile_id=(profile.group(1) if profile else request.query_params.get("profile_id")),
            )
            started = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("request failed", extra={"method": request.method, "path": path})
                raise
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
