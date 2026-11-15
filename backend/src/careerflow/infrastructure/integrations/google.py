"""Google OAuth (authorization code + PKCE), Gmail (read-only) and Google Calendar providers.

Written against the documented REST APIs and verified with recorded responses only; it
has not been exercised against live Google services.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

from careerflow.domain.integrations.ports import (
    CalendarEvent,
    EmailMessage,
    IntegrationError,
    NewCalendarEvent,
)
from careerflow.infrastructure.integrations.http import IntegrationHttp

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105  (public endpoint, not a secret)
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary"

GMAIL_SCOPES: tuple[str, ...] = ("https://www.googleapis.com/auth/gmail.readonly",)
CALENDAR_READ_SCOPES: tuple[str, ...] = ("https://www.googleapis.com/auth/calendar.readonly",)
CALENDAR_WRITE_SCOPES: tuple[str, ...] = ("https://www.googleapis.com/auth/calendar.events",)


def new_pkce() -> tuple[str, str]:
    """(code_verifier, code_challenge) per RFC 7636 (S256)."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class GoogleOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, http: IntegrationHttp) -> None:
        if not client_id or not client_secret:
            raise IntegrationError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not set")
        self._id, self._secret, self._redirect, self._http = client_id, client_secret, redirect_uri, http

    def authorization_url(self, state: str, challenge: str, scopes: tuple[str, ...]) -> str:
        return AUTH_URL + "?" + urlencode(
            {
                "client_id": self._id, "redirect_uri": self._redirect, "response_type": "code",
                "scope": " ".join(scopes), "state": state, "code_challenge": challenge,
                "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent",
            }
        )  # fmt: skip

    def _token(self, form: dict[str, str]) -> dict[str, Any]:
        response = self._http.request("POST", TOKEN_URL, data={**form, "client_id": self._id, "client_secret": self._secret})
        if response.status >= 400:
            raise IntegrationError(f"Google rejected the token request (HTTP {response.status})")
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as error:
            raise IntegrationError("Google returned an unreadable token response") from error
        if not isinstance(data, dict) or "access_token" not in data:
            raise IntegrationError("Google token response had no access token")
        return data

    def exchange_code(self, code: str, verifier: str) -> dict[str, Any]:
        return self._token(
            {"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "redirect_uri": self._redirect}
        )

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        return self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})


def _json(response_text: str, what: str) -> dict[str, Any]:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise IntegrationError(f"{what}: unreadable response") from error
    if not isinstance(data, dict):
        raise IntegrationError(f"{what}: unexpected response shape")
    return data


def _check(status: int, what: str) -> None:
    if status == 401:
        raise IntegrationError(f"{what}: authorization expired or revoked (HTTP 401); reconnect the account")
    if status == 429:
        raise IntegrationError(f"{what}: rate limited (HTTP 429)")
    if status >= 400:
        raise IntegrationError(f"{what}: HTTP {status}")


class GmailProvider:
    """Read-only. The only scope requested is gmail.readonly, so even a bug cannot send mail."""

    name = "gmail"
    scopes: tuple[str, ...] = GMAIL_SCOPES

    def __init__(self, access_token: str, http: IntegrationHttp) -> None:
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._http = http

    def list_messages(self, since: datetime | None = None, limit: int = 50) -> Iterator[EmailMessage]:
        params: dict[str, Any] = {"maxResults": limit}
        if since is not None:
            params["q"] = f"after:{int(since.timestamp())}"
        listing = self._http.request("GET", f"{GMAIL}/messages", headers=self._headers, params=params)
        _check(listing.status, "Gmail list")
        for ref in _json(listing.text, "Gmail list").get("messages", []):
            response = self._http.request(
                "GET", f"{GMAIL}/messages/{ref['id']}", headers=self._headers,
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )  # fmt: skip
            _check(response.status, "Gmail message")
            data = _json(response.text, "Gmail message")
            headers = {h["name"].lower(): h["value"] for h in data.get("payload", {}).get("headers", [])}
            received = _gmail_date(data, headers)
            yield EmailMessage(
                id=str(data["id"]),
                thread_id=data.get("threadId"),
                sender=parseaddr(headers.get("from", ""))[1].lower(),
                subject=headers.get("subject", ""),
                received_at=received,
                snippet=str(data.get("snippet", "")),
            )


def _gmail_date(data: dict[str, Any], headers: dict[str, str]) -> datetime:
    if "internalDate" in data:
        return datetime.fromtimestamp(int(data["internalDate"]) / 1000, UTC)
    try:
        parsed = parsedate_to_datetime(headers.get("date", ""))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


class GoogleCalendarProvider:
    name = "google_calendar"

    def __init__(self, access_token: str, http: IntegrationHttp) -> None:
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._http = http

    def list_events(self, since: datetime | None = None, limit: int = 100) -> Iterator[CalendarEvent]:
        since = since or (datetime.now(UTC) - timedelta(days=1))
        response = self._http.request(
            "GET", f"{CALENDAR}/events", headers=self._headers,
            params={"timeMin": _iso(since), "maxResults": limit, "singleEvents": "true", "orderBy": "startTime"},
        )  # fmt: skip
        _check(response.status, "Calendar list")
        for item in _json(response.text, "Calendar list").get("items", []):
            start = (item.get("start") or {}).get("dateTime")
            if not start or item.get("status") == "cancelled":
                continue  # all-day or cancelled events are not interviews
            end = (item.get("end") or {}).get("dateTime")
            updated = item.get("updated")
            yield CalendarEvent(
                id=str(item["id"]),
                title=str(item.get("summary", "")),
                starts_at=datetime.fromisoformat(start.replace("Z", "+00:00")),
                ends_at=datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None,
                attendees=tuple(a["email"].lower() for a in item.get("attendees", []) if a.get("email")),
                description=str(item.get("description", "")),
                location=item.get("location"),
                meeting_url=item.get("hangoutLink"),
                updated_at=datetime.fromisoformat(updated.replace("Z", "+00:00")) if updated else None,
            )

    @staticmethod
    def _body(event: NewCalendarEvent) -> dict[str, Any]:
        return {
            "summary": event.title,
            "description": event.description,
            "start": {"dateTime": _iso(event.starts_at)},
            "end": {"dateTime": _iso(event.ends_at or event.starts_at + timedelta(hours=1))},
            "attendees": [{"email": a} for a in event.attendees],
        }

    def create_event(self, event: NewCalendarEvent) -> str:
        response = self._http.request("POST", f"{CALENDAR}/events", headers=self._headers, json=self._body(event))
        _check(response.status, "Calendar create")
        return str(_json(response.text, "Calendar create")["id"])

    def update_event(self, event_id: str, event: NewCalendarEvent) -> None:
        response = self._http.request("PATCH", f"{CALENDAR}/events/{event_id}", headers=self._headers, json=self._body(event))
        _check(response.status, "Calendar update")
