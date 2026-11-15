"""Email and calendar integration ports (plan sections 4.4, 31 Phases 12-13).

Safety by construction:
* ``EmailProvider`` is read-only. It has no send/draft-in-mailbox capability, and the OAuth
  scope we request is read-only too. Replies are drafted locally for the user to send.
* ``CalendarProvider`` can write, but only ``CalendarWriteService`` calls those methods, and
  only for a request the user explicitly approved.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class IntegrationError(Exception):
    """Provider failure. Messages never contain tokens."""


class NotConnectedError(IntegrationError):
    pass


@dataclass(frozen=True)
class EmailMessage:
    """What we keep to *recognise* a message: ids and routing facts, never the body."""

    id: str
    thread_id: str | None
    sender: str  # bare address, lower-cased
    subject: str  # used for classification only; not stored
    received_at: datetime
    snippet: str = ""  # provider-supplied preview; used for classification only; not stored


class EmailProvider(Protocol):
    name: str
    scopes: tuple[str, ...]  # must all be read-only (tested)

    def list_messages(self, since: datetime | None = None, limit: int = 50) -> Iterator[EmailMessage]: ...


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    attendees: tuple[str, ...] = ()
    description: str = ""
    location: str | None = None
    meeting_url: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class NewCalendarEvent:
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    attendees: tuple[str, ...] = ()
    description: str = ""


class CalendarProvider(Protocol):
    name: str

    def list_events(self, since: datetime | None = None, limit: int = 100) -> Iterator[CalendarEvent]: ...

    # Writes. Only CalendarWriteService may call these, and only with an approved request.
    def create_event(self, event: NewCalendarEvent) -> str: ...

    def update_event(self, event_id: str, event: NewCalendarEvent) -> None: ...


@dataclass
class EmailClassification:
    kind: str  # interview_request | rejection | offer | recruiter_outreach | other
    reasons: list[str] = field(default_factory=list)


@dataclass
class MatchCandidate:
    application_id: str
    score: float
    reasons: list[str]
