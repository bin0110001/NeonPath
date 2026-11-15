"""Offline providers for tests and demo mode (fictional data only)."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import datetime

from careerflow.domain.integrations.ports import CalendarEvent, EmailMessage, NewCalendarEvent


class FixtureEmailProvider:
    name = "fixture_email"
    scopes = ("fixture.readonly",)

    def __init__(self, messages: list[EmailMessage] | None = None) -> None:
        self.messages = list(messages or [])
        self.calls = 0

    def list_messages(self, since: datetime | None = None, limit: int = 50) -> Iterator[EmailMessage]:
        self.calls += 1
        for message in self.messages[:limit]:
            if since is None or message.received_at >= since:
                yield message


class FixtureCalendarProvider:
    name = "fixture_calendar"

    def __init__(self, events: list[CalendarEvent] | None = None) -> None:
        self.events = list(events or [])
        self.created: list[NewCalendarEvent] = []
        self.updated: list[tuple[str, NewCalendarEvent]] = []
        self._ids = itertools.count(1)

    def list_events(self, since: datetime | None = None, limit: int = 100) -> Iterator[CalendarEvent]:
        for event in self.events[:limit]:
            if since is None or event.starts_at >= since:
                yield event

    def create_event(self, event: NewCalendarEvent) -> str:
        self.created.append(event)
        return f"fixture-event-{next(self._ids)}"

    def update_event(self, event_id: str, event: NewCalendarEvent) -> None:
        self.updated.append((event_id, event))
