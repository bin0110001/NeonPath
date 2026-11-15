"""Classify messages and match messages/events to applications. Pure logic.

Matching is conservative and explainable: every candidate carries the reasons that produced
its score, and only candidates above ``MIN_SCORE`` are returned. The user can always
override a link.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from careerflow.domain.evaluations.service import contains_term, normalize_text
from careerflow.domain.integrations.ports import (
    CalendarEvent,
    EmailClassification,
    EmailMessage,
    MatchCandidate,
)

MIN_SCORE = 0.5
FREE_MAIL = frozenset({"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "proton.me", "protonmail.com", "aol.com"})

RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("offer", ("pleased to offer", "offer letter", "we would like to offer", "extend an offer", "job offer")),
    ("rejection", (
        "unfortunately", "regret to inform", "decided to move forward with other", "not be moving forward",
        "will not be proceeding", "other candidates", "position has been filled",
    )),  # fmt: skip
    ("interview_request", (
        "schedule an interview", "interview with", "like to invite you", "availability for a call",
        "phone screen", "technical interview", "next round", "book a time", "calendar invite",
    )),  # fmt: skip
    ("recruiter_outreach", ("came across your profile", "exciting opportunity", "are you open to", "reaching out")),
)


@dataclass(frozen=True)
class ApplicationFacts:
    """What we know about one application, for matching."""

    application_id: str
    company: str
    job_title: str
    company_domain: str | None = None
    contact_emails: tuple[str, ...] = ()
    thread_ids: tuple[str, ...] = ()


def classify_email(message: EmailMessage) -> EmailClassification:
    text = f"{message.subject}\n{message.snippet}".lower()
    # an offer or rejection outranks a mention of "interview" in the same message
    for kind, phrases in RULES:
        hits = [p for p in phrases if p in text]
        if hits:  # name the rule that fired, never quote the message
            return EmailClassification(kind, [f"{len(hits)} {kind.replace('_', ' ')} phrase(s) recognised"])
    return EmailClassification("other")


def _domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower() if "@" in address else ""


def _company_in(text: str, company: str) -> bool:
    name = normalize_text(re.sub(r"\b(inc|llc|ltd|gmbh|corp|corporation|co|company|plc)\b\.?", "", company, flags=re.I))
    return bool(name) and contains_term(normalize_text(text), name)


def match_email(message: EmailMessage, applications: list[ApplicationFacts]) -> list[MatchCandidate]:
    found: list[MatchCandidate] = []
    domain = _domain(message.sender)
    text = f"{message.subject}\n{message.snippet}"
    for app in applications:
        score, reasons = 0.0, []
        if message.thread_id and message.thread_id in app.thread_ids:
            score, reasons = 1.0, ["same conversation as an earlier linked message"]
        if message.sender in {c.lower() for c in app.contact_emails}:
            score = max(score, 0.9)
            reasons.append("sent by a contact on this application")
        if app.company_domain and domain == app.company_domain.lower():
            score = max(score, 0.8)
            reasons.append(f"sender domain matches {app.company_domain}")
        elif domain and domain not in FREE_MAIL and _company_in(domain.split(".")[0], app.company):
            score = max(score, 0.6)
            reasons.append("sender domain resembles the company name")
        if _company_in(text, app.company):
            score += 0.35
            reasons.append(f"mentions {app.company}")
        if contains_term(normalize_text(text), normalize_text(app.job_title)):
            score += 0.2
            reasons.append("mentions the job title")
        if score >= MIN_SCORE:
            found.append(MatchCandidate(app.application_id, round(min(score, 1.0), 2), reasons))
    return sorted(found, key=lambda c: -c.score)


def match_event(event: CalendarEvent, applications: list[ApplicationFacts]) -> list[MatchCandidate]:
    found: list[MatchCandidate] = []
    text = f"{event.title}\n{event.description}"
    attendees = {a.lower() for a in event.attendees}
    for app in applications:
        score, reasons = 0.0, []
        if attendees & {c.lower() for c in app.contact_emails}:
            score += 0.8
            reasons.append("an attendee is a contact on this application")
        if app.company_domain and any(_domain(a) == app.company_domain.lower() for a in attendees):
            score += 0.6
            reasons.append(f"an attendee is from {app.company_domain}")
        if _company_in(text, app.company):
            score += 0.5
            reasons.append(f"mentions {app.company}")
        if contains_term(normalize_text(text), normalize_text(app.job_title)):
            score += 0.15
            reasons.append("mentions the job title")
        if any(w in text.lower() for w in ("interview", "screen", "technical", "onsite", "panel")):
            score += 0.1
            reasons.append("looks like an interview")
        if score >= MIN_SCORE:
            found.append(MatchCandidate(app.application_id, round(min(score, 1.0), 2), reasons))
    return sorted(found, key=lambda c: -c.score)
