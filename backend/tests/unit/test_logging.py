import io
import json
import logging
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from careerflow.infrastructure.logging import (
    REDACTED,
    Redactor,
    bind_log_context,
    clear_log_context,
    configure_logging,
    current_log_context,
    log_context,
    secrets_from_url,
)
from careerflow.main import create_app

SECRET = "sk-live-9f8e7d6c5b4a"


@pytest.fixture
def stream() -> Generator[io.StringIO]:
    buffer = io.StringIO()
    handler = configure_logging("DEBUG", secrets=[SECRET], stream=buffer)
    yield buffer
    logging.getLogger().removeHandler(handler)
    clear_log_context()


def lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_output_is_json_with_bound_context(stream: io.StringIO) -> None:
    with log_context(request_id="r1", profile_id="p1", job_id="j1", source_adapter="rss", task_id="t1"):
        logging.getLogger("x").info("hello %s", "world", extra={"count": 3})
    (record,) = lines(stream)
    assert record["message"] == "hello world"
    assert record["level"] == "INFO"
    assert record["count"] == 3
    assert {k: record[k] for k in ("request_id", "profile_id", "job_id", "source_adapter", "task_id")} == {
        "request_id": "r1", "profile_id": "p1", "job_id": "j1", "source_adapter": "rss", "task_id": "t1",
    }  # fmt: skip
    assert current_log_context() == {}  # context manager restores state


def test_unknown_context_field_is_rejected() -> None:
    with pytest.raises(ValueError):
        bind_log_context(password="x")


def test_configured_secret_never_appears(stream: io.StringIO) -> None:
    log = logging.getLogger("x")
    log.info("calling provider with key %s", SECRET)
    log.info("plain %s", "text", extra={"payload": {"key": SECRET, "nested": [SECRET]}})
    log.warning(f"header was {SECRET}")
    try:
        raise RuntimeError(f"failed using {SECRET}")
    except RuntimeError:
        log.exception("boom")
    output = stream.getvalue()
    assert SECRET not in output
    assert REDACTED in output
    assert len(lines(stream)) == 4


@pytest.mark.parametrize(
    ("text", "leaked"),
    [
        ("Authorization: Bearer abcdef1234567890", "abcdef1234567890"),
        ("api_key=hunter2hunter2", "hunter2hunter2"),
        ('{"password": "s3cret-value"}', "s3cret-value"),
        ("refresh_token: zzzzzzzzzzzz", "zzzzzzzzzzzz"),
        ("contact jane.doe@example.com now", "jane.doe@example.com"),
        ("postgresql+psycopg://careerflow:pa55word@db:5432/careerflow", "pa55word"),
    ],
)
def test_pattern_redaction(text: str, leaked: str) -> None:
    redacted = Redactor().redact(text)
    assert leaked not in redacted
    assert REDACTED in redacted


def test_innocent_text_is_untouched() -> None:
    text = "Evaluated job 123 for profile abc: score 0.82"
    assert Redactor().redact(text) == text


def test_database_password_is_extracted_from_url() -> None:
    assert secrets_from_url("postgresql+psycopg://u:pw-12345@db:5432/x") == ["pw-12345"]
    assert secrets_from_url("sqlite://") == []


def test_every_request_log_line_has_a_request_id(stream: io.StringIO) -> None:
    client = TestClient(create_app())
    # create_app() reconfigures logging with its own stream; attach ours as well.
    handler = logging.StreamHandler(stream)
    from careerflow.infrastructure.logging import JsonFormatter, RedactionFilter

    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    logging.getLogger().addHandler(handler)
    try:
        response = client.get("/health/live", headers={"X-Request-ID": "abc-123"})
        other = client.get("/health/live")
        bad = client.get("/health/live", headers={"X-Request-ID": 'evil"\n{"x":1}'})
    finally:
        logging.getLogger().removeHandler(handler)
    assert response.headers["X-Request-ID"] == "abc-123"
    assert other.headers["X-Request-ID"] and other.headers["X-Request-ID"] != "abc-123"
    assert bad.headers["X-Request-ID"] != 'evil"\n{"x":1}'
    records = [r for r in lines(stream) if r["logger"] == "careerflow.request"]
    assert len(records) == 3
    assert all(r.get("request_id") for r in records)
    assert records[0]["request_id"] == "abc-123"
    assert records[0]["path"] == "/health/live" and records[0]["status"] == 200


def test_ids_from_the_path_are_bound(stream: io.StringIO) -> None:
    client = TestClient(create_app())
    job_id = "11111111-1111-1111-1111-111111111111"
    profile_id = "22222222-2222-2222-2222-222222222222"
    handler = logging.StreamHandler(stream)
    from careerflow.infrastructure.logging import JsonFormatter

    handler.setFormatter(JsonFormatter())
    logging.getLogger().addHandler(handler)
    try:
        client.get(f"/api/v1/jobs/{job_id}/workflow", params={"profile_id": profile_id})
    except Exception:  # no database in unit tests: the request log must still carry the ids
        pass
    finally:
        logging.getLogger().removeHandler(handler)
    record = next(r for r in lines(stream) if r["logger"] == "careerflow.request")
    assert record["job_id"] == job_id
    assert record["profile_id"] == profile_id
