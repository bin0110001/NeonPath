"""Structured JSON logging with request context and secret redaction (plan section 20).

* Every record is one JSON object carrying the contextual ids bound for the current
  request/task (request_id, task_id, profile_id, job_id, source_adapter).
* A redaction filter runs on the handler, so records from third-party libraries are
  covered as well: configured secret values, credentials inside the database URL,
  bearer tokens, ``key=value`` secrets and e-mail addresses never reach the output.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO
from urllib.parse import urlsplit

CONTEXT_FIELDS = ("request_id", "task_id", "profile_id", "job_id", "source_adapter")
REDACTED = "[REDACTED]"

_context: ContextVar[dict[str, str] | None] = ContextVar("log_context", default=None)

_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_KEYED = re.compile(
    r"(?i)\b(authorization|api[_-]?key|apikey|password|passwd|secret|token|access[_-]?token"
    r"|refresh[_-]?token|client[_-]?secret)\b(\"?\s*[:=]\s*\"?)[^\s\"',;&]+"
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_CREDS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*)://[^\s:@/]+:[^\s@/]+@")


def bind_log_context(**values: str | None) -> None:
    """Add ids (only ``CONTEXT_FIELDS``) to every log line of the current context."""
    merged = dict(_context.get() or {})
    for key, value in values.items():
        if key not in CONTEXT_FIELDS:
            raise ValueError(f"unknown log context field: {key}")
        if value is not None:
            merged[key] = value
    _context.set(merged)


def current_log_context() -> dict[str, str]:
    return dict(_context.get() or {})


def clear_log_context() -> None:
    _context.set(None)


@contextmanager
def log_context(**values: str | None) -> Iterator[None]:
    token = _context.set(dict(_context.get() or {}))
    try:
        bind_log_context(**values)
        yield
    finally:
        _context.reset(token)


def secrets_from_url(url: str) -> list[str]:
    """Credential parts of a connection URL that must never be logged."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return []
    return [value for value in (parts.password,) if value]


class Redactor:
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self._secrets: set[str] = set()
        self.add(secrets)

    def add(self, secrets: Iterable[str]) -> None:
        self._secrets |= {s for s in secrets if s and len(s) >= 4}

    def redact(self, text: str) -> str:
        # Longest first so a secret that contains another is replaced whole.
        for secret in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(secret, REDACTED)
        text = _URL_CREDS.sub(lambda m: f"{m.group(1)}://{REDACTED}@", text)
        text = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
        text = _KEYED.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
        return _EMAIL.sub(REDACTED, text)

    def redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {k: self.redact_value(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [self.redact_value(v) for v in value]
        return value


_redactor = Redactor()


def get_redactor() -> Redactor:
    return _redactor


class RedactionFilter(logging.Filter):
    """Redacts the formatted message, exception text and extra fields of every record."""

    def __init__(self, redactor: Redactor | None = None) -> None:
        super().__init__()
        self.redactor = redactor or _redactor

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redactor.redact(record.getMessage())
        record.args = None
        if record.exc_info and record.exc_info[1] is not None:
            record.exc_text = self.redactor.redact(
                logging.Formatter().formatException(record.exc_info)
            )
            record.exc_info = None
        for key, value in list(record.__dict__.items()):
            if key not in _STANDARD_ATTRS:
                record.__dict__[key] = self.redactor.redact_value(value)
        return True


_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = current_log_context()
        for field in CONTEXT_FIELDS:
            if field in context:
                payload[field] = context[field]
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_text:
            payload["exception"] = record.exc_text
        elif record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(
    level: str = "INFO", secrets: Iterable[str] = (), stream: TextIO | None = None
) -> logging.Handler:
    """Install the JSON handler on the root logger and route uvicorn through it."""
    _redactor.add(secrets)
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter(_redactor))
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_careerflow", False):  # replace only our own handler
            root.removeHandler(existing)
    handler._careerflow = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        library = logging.getLogger(name)
        library.handlers = []
        library.propagate = True
    logging.getLogger("uvicorn.access").disabled = True  # the request middleware logs instead
    return handler
