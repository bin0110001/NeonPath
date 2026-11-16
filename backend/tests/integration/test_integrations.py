from __future__ import annotations

import ast
import inspect
import io
import json
import logging
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import careerflow
from careerflow.api.integrations import get_accounts, get_session
from careerflow.api.profiles import get_session as profiles_session
from careerflow.api.tracking import get_session as tracking_session
from careerflow.application.integrations.accounts import AccountService
from careerflow.application.integrations.calendar_service import CalendarService
from careerflow.application.integrations.email_service import DRAFT_NOTICE, EmailService
from careerflow.domain.integrations.matching import (
    ApplicationFacts,
    classify_email,
    match_email,
    match_event,
)
from careerflow.domain.integrations.ports import (
    CalendarEvent,
    EmailMessage,
    EmailProvider,
    IntegrationError,
)
from careerflow.infrastructure.database.models import (
    ApplicationModel,
    Base,
    CalendarWriteRequestModel,
    EmailLinkModel,
    FollowUpModel,
    IntegrationAccountModel,
    InterviewModel,
    JobModel,
    ProfileModel,
)
from careerflow.infrastructure.integrations.fixtures import (
    FixtureCalendarProvider,
    FixtureEmailProvider,
)
from careerflow.infrastructure.integrations.google import GmailProvider, GoogleCalendarProvider
from careerflow.infrastructure.jobsources.http import HttpResponse
from careerflow.infrastructure.logging import JsonFormatter, RedactionFilter
from careerflow.infrastructure.security.crypto import TokenCipher, generate_key
from careerflow.main import create_app
from careerflow.settings import Settings

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
KEY = generate_key()
ACCESS, REFRESH = "ya29.ACCESS-TOKEN-SECRET-123", "1//REFRESH-TOKEN-SECRET-456"


def msg(i: str, sender: str, subject: str, snippet: str = "", thread: str | None = None, at: datetime = NOW) -> EmailMessage:
    return EmailMessage(i, thread, sender, subject, at, snippet)


APP = ApplicationFacts("app1", "Contoso Labs", "Platform Engineer", "contoso.com", ("riley@contoso.com",))
OTHER = ApplicationFacts("app2", "Fabrikam", "Data Scientist", None, ())


# --- classification and matching (pure) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "snippet", "kind"),
    [
        ("Interview with Contoso", "We would like to invite you to schedule an interview", "interview_request"),
        ("Your application", "Unfortunately we have decided to move forward with other candidates", "rejection"),
        ("Offer", "We are pleased to offer you the position", "offer"),
        ("Opportunity", "I came across your profile and have an exciting opportunity", "recruiter_outreach"),
        ("Weekly newsletter", "10 tips for your desk", "other"),
        ("Next steps", "Unfortunately the interview round was cancelled; we will not be proceeding", "rejection"),
    ],
)
def test_classification(subject: str, snippet: str, kind: str) -> None:
    assert classify_email(msg("1", "a@b.com", subject, snippet)).kind == kind


def test_email_matching_uses_domain_contact_thread_and_text() -> None:
    by_domain = match_email(msg("1", "hr@contoso.com", "Hello"), [APP, OTHER])
    assert [c.application_id for c in by_domain] == ["app1"] and "sender domain matches contoso.com" in by_domain[0].reasons[0]
    by_contact = match_email(msg("2", "riley@contoso.com", "Quick note"), [APP])
    assert by_contact[0].score >= 0.9 and any("contact" in r for r in by_contact[0].reasons)
    by_thread = match_email(msg("3", "x@gmail.com", "Re: hi", thread="t9"), [ApplicationFacts("app1", "Contoso", "X", None, (), ("t9",))])
    assert by_thread[0].score == 1.0
    by_text = match_email(msg("4", "jobs@mail.example", "Contoso Labs: Platform Engineer interview"), [APP, OTHER])
    assert [c.application_id for c in by_text] == ["app1"]


def test_free_mail_domains_and_unrelated_senders_do_not_match() -> None:
    assert match_email(msg("1", "someone@gmail.com", "Hello there"), [APP, OTHER]) == []
    assert match_email(msg("2", "news@other.org", "Contoso is mentioned only in passing? no"), [OTHER]) == []


def test_event_matching() -> None:
    event = CalendarEvent("e1", "Technical interview - Contoso Labs", NOW, attendees=("riley@contoso.com", "me@x.org"))
    assert [c.application_id for c in match_event(event, [APP, OTHER])] == ["app1"]
    nothing = CalendarEvent("e2", "Dentist", NOW)
    assert match_event(nothing, [APP, OTHER]) == []
    by_domain = CalendarEvent("e3", "Call", NOW, attendees=("hr@contoso.com",))
    assert match_event(by_domain, [APP]) == [] or match_event(by_domain, [APP])[0].application_id == "app1"


# --- environment ---------------------------------------------------------------------------------------


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def world(session: Session) -> dict[str, str]:
    a, b = ProfileModel(slug="a", display_name="Ada Applicant"), ProfileModel(slug="b", display_name="Bo Other")
    job = JobModel(title="Platform Engineer", company="Contoso Labs", company_domain="contoso.com", description_text="d")
    session.add_all([a, b, job])
    session.flush()
    app_a = ApplicationModel(profile_id=a.id, job_id=job.id)
    app_b = ApplicationModel(profile_id=b.id, job_id=job.id)
    session.add_all([app_a, app_b])
    session.commit()
    return {"a": a.id, "b": b.id, "app_a": app_a.id, "app_b": app_b.id, "job": job.id}


# --- email --------------------------------------------------------------------------------------------


def test_sync_stores_ids_not_message_content(session: Session) -> None:
    w = world(session)
    provider = FixtureEmailProvider(
        [
            msg("m1", "hr@contoso.com", "Interview invitation", "We would like to schedule an interview next week", "t1"),
            msg("m2", "random@spam.io", "Buy now", "cheap watches"),
            msg("m3", "recruiter@staffing.example", "Role", "I came across your profile, exciting opportunity"),
        ]
    )
    result = EmailService(session).sync(w["a"], provider, since=NOW - timedelta(days=1))
    assert (result.scanned, result.linked, result.unmatched) == (3, 1, 1)  # spam is not recorded at all
    links = {link.message_id: link for link in session.scalars(select(EmailLinkModel))}
    assert set(links) == {"m1", "m3"}
    assert links["m1"].application_id == w["app_a"] and links["m1"].classification == "interview_request"
    assert links["m3"].application_id is None and links["m3"].classification == "recruiter_outreach"
    columns = {c.name for c in EmailLinkModel.__table__.columns}
    assert not columns & {"subject", "body", "snippet", "content", "text", "sender"}  # no mailbox copies
    dumped = json.dumps([[getattr(item, c) for c in columns if c not in ("received_at", "created_at")] for item in links.values()], default=str)
    assert "schedule an interview" not in dumped and "Interview invitation" not in dumped and "recruiter@staffing" not in dumped


def test_sync_is_idempotent_and_thread_continuity_links_followups(session: Session) -> None:
    w = world(session)
    provider = FixtureEmailProvider([msg("m1", "hr@contoso.com", "Interview", "schedule an interview", "t1")])
    svc = EmailService(session)
    svc.sync(w["a"], provider, since=NOW - timedelta(days=1))
    provider.messages.append(msg("m2", "someone.else@gmail.com", "Re: Interview", "Does Tuesday work for the next round?", "t1"))
    again = svc.sync(w["a"], provider, since=NOW - timedelta(days=1))
    assert again.skipped_known == 1 and again.linked == 1
    assert session.scalar(select(func.count()).select_from(EmailLinkModel)) == 2
    reply = session.scalars(select(EmailLinkModel).where(EmailLinkModel.message_id == "m2")).one()
    assert reply.application_id == w["app_a"] and any("conversation" in r for r in reply.reasons)


def test_link_review_is_profile_scoped(session: Session) -> None:
    w = world(session)
    EmailService(session).sync(w["a"], FixtureEmailProvider([msg("m1", "hr@contoso.com", "Interview", "schedule an interview")]), NOW - timedelta(days=1))
    link = session.scalars(select(EmailLinkModel)).one()
    svc = EmailService(session)
    from careerflow.application.profiles.service import ProfileItemNotFoundError

    for call in (lambda: svc.confirm(w["b"], link.id), lambda: svc.dismiss(w["b"], link.id), lambda: svc.draft_reply(w["b"], link.id)):
        with pytest.raises(ProfileItemNotFoundError):
            call()
    assert svc.list_links(w["b"]) == []
    with pytest.raises(ProfileItemNotFoundError):
        svc.confirm(w["a"], link.id, application_id=w["app_b"])  # another profile's application
    assert svc.confirm(w["a"], link.id).status == "CONFIRMED"
    assert svc.dismiss(w["a"], link.id).status == "DISMISSED"


def test_unmatched_link_needs_an_application_to_confirm(session: Session) -> None:
    w = world(session)
    EmailService(session).sync(w["a"], FixtureEmailProvider([msg("m3", "r@staffing.example", "Role", "I came across your profile, exciting opportunity")]), NOW - timedelta(days=1))
    link = session.scalars(select(EmailLinkModel)).one()
    with pytest.raises(ValueError, match="choose an application"):
        EmailService(session).confirm(w["a"], link.id)
    assert EmailService(session).confirm(w["a"], link.id, w["app_a"]).application_id == w["app_a"]


def test_drafts_are_local_and_labelled(session: Session) -> None:
    w = world(session)
    svc = EmailService(session)
    svc.sync(w["a"], FixtureEmailProvider([msg("m1", "hr@contoso.com", "Offer", "We are pleased to offer you the role")]), NOW - timedelta(days=1))
    link = session.scalars(select(EmailLinkModel)).one()
    draft = svc.draft_reply(w["a"], link.id)
    assert draft.body.startswith(DRAFT_NOTICE) and "Platform Engineer" in draft.body and "Ada Applicant" in draft.body
    assert [d.id for d in svc.drafts(w["a"], link.id)] == [draft.id]


# --- read-only / no-send guarantees ---------------------------------------------------------------------


def test_the_email_port_cannot_send_and_scopes_are_read_only() -> None:
    members = {n.lower() for n, _ in inspect.getmembers(EmailProvider) if not n.startswith("_")}
    assert members == {"list_messages"} and set(EmailProvider.__annotations__) == {"name", "scopes"}  # no send/reply/draft
    for provider_scopes in (GmailProvider.scopes, FixtureEmailProvider.scopes):
        assert all("readonly" in s for s in provider_scopes)


def test_no_code_path_sends_email() -> None:
    root = Path(careerflow.__file__).parent
    forbidden_imports = {"smtplib", "imaplib", "poplib"}
    forbidden_text = ("messages/send", "messages.send", "drafts/send", "sendmail", "send_message", "send_email", "gmail.send", "gmail.compose", "gmail.modify")
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)} | {
            (n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        }
        assert not imported & forbidden_imports, path
        if path.name != "test_integrations.py":
            for needle in forbidden_text:
                assert needle not in source, f"{needle!r} found in {path}"


class RecordingHttp:
    def __init__(self, routes: dict[str, HttpResponse]) -> None:
        self.routes, self.calls = routes, []

    def request(self, method: str, url: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None, data: dict[str, str] | None = None, timeout: float = 15.0) -> HttpResponse:
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "params": params, "json": json, "data": data})
        for fragment, response in self.routes.items():
            if fragment in url:
                return response
        return HttpResponse(404, "{}")


def ok(payload: dict[str, Any], status: int = 200) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload))


GMAIL_LIST = {"messages": [{"id": "g1", "threadId": "t1"}]}
GMAIL_MSG = {
    "id": "g1", "threadId": "t1", "snippet": "We would like to schedule an interview", "internalDate": str(int(NOW.timestamp() * 1000)),
    "payload": {"headers": [{"name": "From", "value": "Riley Recruiter <Riley@Contoso.com>"}, {"name": "Subject", "value": "Interview invitation"}, {"name": "Date", "value": "Mon, 1 Jun 2026 12:00:00 +0000"}]},
}


def test_gmail_provider_only_reads(session: Session) -> None:
    http = RecordingHttp({"/messages/g1": ok(GMAIL_MSG), "/messages": ok(GMAIL_LIST)})
    messages = list(GmailProvider(ACCESS, http).list_messages(NOW - timedelta(days=1), 10))
    assert [(m.id, m.thread_id, m.sender, m.subject) for m in messages] == [("g1", "t1", "riley@contoso.com", "Interview invitation")]
    assert {c["method"] for c in http.calls} == {"GET"}
    assert all(c["headers"] == {"Authorization": f"Bearer {ACCESS}"} for c in http.calls)
    assert "after:" in http.calls[0]["params"]["q"] and ACCESS not in json.dumps([c["url"] for c in http.calls])


@pytest.mark.parametrize(("status", "fragment"), [(401, "reconnect"), (429, "rate limited"), (500, "HTTP 500")])
def test_provider_errors_are_readable_and_secret_free(status: int, fragment: str) -> None:
    http = RecordingHttp({"/messages": HttpResponse(status, f"echo {ACCESS}")})
    with pytest.raises(IntegrationError) as info:
        list(GmailProvider(ACCESS, http).list_messages())
    assert fragment in str(info.value) and ACCESS not in str(info.value)


# --- OAuth, tokens, demo mode ------------------------------------------------------------------------------


def settings(**kw: Any) -> Settings:
    base: dict[str, Any] = {"integration_encryption_key": KEY, "google_client_id": "cid", "google_client_secret": "csecret", "demo_mode": False}
    base.update(kw)
    return Settings(**base)


TOKENS = {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600}


def test_connect_flow_uses_pkce_readonly_scopes_and_encrypts_tokens(session: Session) -> None:
    w = world(session)
    http = RecordingHttp({"oauth2.googleapis.com/token": ok(TOKENS)})
    accounts = AccountService(session, settings(), http, clock=lambda: NOW)
    url = accounts.start(w["a"], "email")
    query = parse_qs(urlparse(url).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert query["code_challenge_method"] == ["S256"] and query["access_type"] == ["offline"] and "code_challenge" in query
    state = query["state"][0]

    account = accounts.complete(state, "auth-code")
    form = http.calls[0]["data"]
    assert form["grant_type"] == "authorization_code" and form["code"] == "auth-code" and len(form["code_verifier"]) >= 43
    assert account.enc_access_token != ACCESS and account.enc_refresh_token != REFRESH
    stored = " ".join(str(getattr(account, c.name)) for c in IntegrationAccountModel.__table__.columns)
    assert ACCESS not in stored and REFRESH not in stored
    cipher = TokenCipher(KEY)
    assert cipher.decrypt(account.enc_access_token) == ACCESS and cipher.decrypt(account.enc_refresh_token or "") == REFRESH
    with pytest.raises(IntegrationError, match="unknown or already used"):
        accounts.complete(state, "auth-code")  # state is single-use


def test_status_never_contains_tokens(session: Session) -> None:
    w = world(session)
    http = RecordingHttp({"oauth2.googleapis.com/token": ok(TOKENS)})
    accounts = AccountService(session, settings(), http, clock=lambda: NOW)
    accounts.complete(parse_qs(urlparse(accounts.start(w["a"], "email")).query)["state"][0], "c")
    status = accounts.status(w["a"])
    assert [(s.kind, s.connected) for s in status] == [("email", True), ("calendar", False)]
    assert ACCESS not in repr(status) and REFRESH not in repr(status)
    accounts.disconnect(w["a"], "email")
    assert not accounts.status(w["a"])[0].connected


def test_expired_access_token_is_refreshed(session: Session) -> None:
    w = world(session)
    clock = [NOW]
    http = RecordingHttp({"oauth2.googleapis.com/token": ok(TOKENS)})
    accounts = AccountService(session, settings(), http, clock=lambda: clock[0])
    accounts.complete(parse_qs(urlparse(accounts.start(w["a"], "email")).query)["state"][0], "c")
    http.routes["oauth2.googleapis.com/token"] = ok({"access_token": "NEW-ACCESS", "expires_in": 3600})
    http.routes["/messages"] = ok({"messages": []})
    clock[0] = NOW + timedelta(hours=2)
    accounts.email_provider(w["a"])
    assert http.calls[-1]["data"]["grant_type"] == "refresh_token" and http.calls[-1]["data"]["refresh_token"] == REFRESH
    account = session.scalars(select(IntegrationAccountModel)).one()
    assert TokenCipher(KEY).decrypt(account.enc_access_token) == "NEW-ACCESS"


def test_calendar_write_scope_only_when_requested(session: Session) -> None:
    w = world(session)
    accounts = AccountService(session, settings(), RecordingHttp({}), clock=lambda: NOW)
    read = parse_qs(urlparse(accounts.start(w["a"], "calendar")).query)["scope"]
    write = parse_qs(urlparse(accounts.start(w["a"], "calendar", allow_writes=True)).query)["scope"]
    assert read == ["https://www.googleapis.com/auth/calendar.readonly"] and write == ["https://www.googleapis.com/auth/calendar.events"]
    with pytest.raises(IntegrationError, match="only calendar"):
        accounts.start(w["a"], "email", allow_writes=True)


def test_missing_key_missing_client_and_demo_mode_block_connecting(session: Session) -> None:
    w = world(session)
    http = RecordingHttp({})
    with pytest.raises(IntegrationError, match="INTEGRATION_ENCRYPTION_KEY"):
        AccountService(session, settings(integration_encryption_key=""), http).start(w["a"], "email")
    with pytest.raises(IntegrationError, match="GOOGLE_CLIENT_ID"):
        AccountService(session, settings(google_client_id=""), http).start(w["a"], "email")
    demo = AccountService(session, settings(demo_mode=True), http)
    with pytest.raises(IntegrationError, match="demo mode"):
        demo.start(w["a"], "email")
    with pytest.raises(IntegrationError, match="demo mode"):
        demo.email_provider(w["a"])
    with pytest.raises(IntegrationError, match="no email account"):
        AccountService(session, settings(), http).email_provider(w["a"])
    assert http.calls == []


def test_tokens_never_reach_the_logs(session: Session) -> None:
    w = world(session)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    old = root.level
    root.setLevel(logging.DEBUG)
    try:
        http = RecordingHttp({"oauth2.googleapis.com/token": ok(TOKENS), "/messages": HttpResponse(401, ACCESS)})
        accounts = AccountService(session, settings(), http, clock=lambda: NOW)
        accounts.complete(parse_qs(urlparse(accounts.start(w["a"], "email")).query)["state"][0], "c")
        with pytest.raises(IntegrationError):
            list(accounts.email_provider(w["a"]).list_messages())
        logging.getLogger("x").error("failed with Authorization: Bearer %s and access_token=%s", ACCESS, REFRESH)
    finally:
        root.removeHandler(handler)
        root.setLevel(old)
    assert ACCESS not in stream.getvalue() and REFRESH not in stream.getvalue()


# --- calendar -----------------------------------------------------------------------------------------------


def cal_event(i: str = "ev1", title: str = "Technical interview - Contoso Labs", hours: int = 48, attendees: tuple[str, ...] = ("riley@contoso.com",), **kw: Any) -> CalendarEvent:
    start = NOW + timedelta(hours=hours)
    return CalendarEvent(i, title, start, start + timedelta(hours=1), attendees, meeting_url="https://meet.example/x", **kw)


def test_import_matches_events_and_never_duplicates(session: Session) -> None:
    w = world(session)
    provider = FixtureCalendarProvider([cal_event(), cal_event("ev2", "Dentist", attendees=())])
    svc = CalendarService(session)
    first = svc.import_events(w["a"], provider, since=NOW - timedelta(days=1))
    assert (first.scanned, first.created, first.unmatched, first.reminders) == (2, 1, 1, 1)
    again = svc.import_events(w["a"], provider, since=NOW - timedelta(days=1))
    assert (again.created, again.updated, again.unchanged, again.reminders) == (0, 0, 1, 0)
    assert session.scalar(select(func.count()).select_from(InterviewModel)) == 1
    assert session.scalar(select(func.count()).select_from(FollowUpModel)) == 1
    interview = session.scalars(select(InterviewModel)).one()
    assert interview.external_event_id == "ev1" and interview.application_id == w["app_a"]
    assert (interview.duration_minutes, interview.participants, interview.meeting_url) == (60, ["riley@contoso.com"], "https://meet.example/x")


def test_moved_events_update_the_interview_and_reminder(session: Session) -> None:
    w = world(session)
    provider = FixtureCalendarProvider([cal_event(hours=48)])
    svc = CalendarService(session)
    svc.import_events(w["a"], provider, since=NOW - timedelta(days=1))
    provider.events = [cal_event(hours=96)]
    result = svc.import_events(w["a"], provider, since=NOW - timedelta(days=1))
    assert (result.created, result.updated) == (0, 1)
    interview = session.scalars(select(InterviewModel)).one()
    reminder = session.scalars(select(FollowUpModel)).one()
    assert reminder.type == "prep" and reminder.status == "OPEN"
    due = reminder.due_at if reminder.due_at.tzinfo else reminder.due_at.replace(tzinfo=UTC)
    assert due == NOW + timedelta(hours=96) - timedelta(days=1)
    assert session.scalar(select(func.count()).select_from(InterviewModel)) == 1 and interview.scheduled_at


def test_events_import_only_into_the_connected_profile(session: Session) -> None:
    w = world(session)
    CalendarService(session).import_events(w["a"], FixtureCalendarProvider([cal_event()]), since=NOW - timedelta(days=1))
    interview = session.scalars(select(InterviewModel)).one()
    assert interview.profile_id == w["a"]
    assert session.scalar(select(func.count()).select_from(InterviewModel).where(InterviewModel.profile_id == w["b"])) == 0


def prepared(session: Session) -> tuple[dict[str, str], FixtureCalendarProvider, CalendarService, InterviewModel]:
    w = world(session)
    interview = InterviewModel(profile_id=w["a"], application_id=w["app_a"], type="coding", scheduled_at=NOW + timedelta(days=2), duration_minutes=45, participants=["riley@contoso.com"])
    session.add(interview)
    session.commit()
    provider = FixtureCalendarProvider()
    return w, provider, CalendarService(session, settings()), interview


def test_nothing_is_written_until_the_user_approves(session: Session) -> None:
    w, provider, svc, interview = prepared(session)
    request = svc.propose(w["a"], interview.id)
    assert request.status == "PENDING" and request.action == "create" and request.payload_json["title"] == "Interview: Platform Engineer at Contoso Labs"
    assert provider.created == [] and provider.updated == []  # proposing writes nothing

    done = svc.approve(w["a"], request.id, provider, writes_allowed=True)
    assert done.status == "DONE" and len(provider.created) == 1 and provider.created[0].title == request.payload_json["title"]
    session.refresh(interview)
    assert interview.external_event_id == "fixture-event-1"
    with pytest.raises(ValueError, match="already DONE"):
        svc.approve(w["a"], request.id, provider, writes_allowed=True)  # cannot be approved twice
    assert len(provider.created) == 1


def test_updating_a_known_event_after_approval_and_reimport_dedupes(session: Session) -> None:
    w, provider, svc, interview = prepared(session)
    svc.approve(w["a"], svc.propose(w["a"], interview.id).id, provider, True)
    interview.scheduled_at = NOW + timedelta(days=3)
    session.commit()
    update = svc.propose(w["a"], interview.id)
    assert update.action == "update" and update.event_id == "fixture-event-1"
    svc.approve(w["a"], update.id, provider, True)
    assert [e for e, _ in provider.updated] == ["fixture-event-1"]
    provider.events = [CalendarEvent("fixture-event-1", "Interview: Platform Engineer at Contoso Labs", NOW + timedelta(days=3), attendees=("riley@contoso.com",))]
    svc.import_events(w["a"], provider, since=NOW - timedelta(days=1))
    assert session.scalar(select(func.count()).select_from(InterviewModel)) == 1  # the event we created is recognised


def test_rejected_requests_never_write(session: Session) -> None:
    w, provider, svc, interview = prepared(session)
    request = svc.propose(w["a"], interview.id)
    assert svc.reject(w["a"], request.id).status == "REJECTED"
    with pytest.raises(ValueError, match="already REJECTED"):
        svc.approve(w["a"], request.id, provider, True)
    assert provider.created == []


def test_read_only_connection_and_demo_mode_block_writes(session: Session) -> None:
    from careerflow.demo import ExternalWritesDisabledError

    w, provider, svc, interview = prepared(session)
    request = svc.propose(w["a"], interview.id)
    with pytest.raises(IntegrationError, match="read-only"):
        svc.approve(w["a"], request.id, provider, writes_allowed=False)
    demo = CalendarService(session, settings(demo_mode=True))
    with pytest.raises(ExternalWritesDisabledError):
        demo.approve(w["a"], request.id, provider, writes_allowed=True)
    assert provider.created == [] and session.get(CalendarWriteRequestModel, request.id).status == "PENDING"  # type: ignore[union-attr]


def test_provider_failure_is_recorded_without_secrets(session: Session) -> None:
    w, provider, svc, interview = prepared(session)

    def boom(event: Any) -> str:
        raise IntegrationError(f"Calendar create: HTTP 500 token={ACCESS}")

    provider.create_event = boom  # type: ignore[method-assign]
    request = svc.propose(w["a"], interview.id)
    done = svc.approve(w["a"], request.id, provider, True)
    assert done.status == "FAILED" and ACCESS not in (done.error or "")


def test_write_requests_are_profile_scoped(session: Session) -> None:
    w, provider, svc, interview = prepared(session)
    request = svc.propose(w["a"], interview.id)
    from careerflow.application.profiles.service import ProfileItemNotFoundError

    with pytest.raises(ProfileItemNotFoundError):
        svc.approve(w["b"], request.id, provider, True)
    with pytest.raises(ProfileItemNotFoundError):
        svc.reject(w["b"], request.id)
    with pytest.raises(ProfileItemNotFoundError):
        svc.propose(w["b"], interview.id)
    assert svc.requests(w["b"]) == [] and provider.created == []


def test_google_calendar_requests_and_responses() -> None:
    items = {"items": [
        {"id": "g1", "summary": "Interview - Contoso Labs", "start": {"dateTime": "2026-06-03T10:00:00Z"}, "end": {"dateTime": "2026-06-03T11:00:00Z"}, "attendees": [{"email": "Riley@Contoso.com"}], "hangoutLink": "https://meet.google.com/x", "updated": "2026-06-01T00:00:00Z"},
        {"id": "g2", "summary": "All day", "start": {"date": "2026-06-04"}},
        {"id": "g3", "summary": "Cancelled", "status": "cancelled", "start": {"dateTime": "2026-06-05T10:00:00Z"}},
    ]}
    http = RecordingHttp({"/events/g1": ok({}), "/events": ok(items)})
    provider = GoogleCalendarProvider(ACCESS, http)
    events = list(provider.list_events(NOW))
    assert [e.id for e in events] == ["g1"] and events[0].attendees == ("riley@contoso.com",) and events[0].meeting_url
    assert http.calls[0]["params"]["singleEvents"] == "true"

    from careerflow.domain.integrations.ports import NewCalendarEvent

    new = NewCalendarEvent("T", NOW, NOW + timedelta(hours=1), ("a@b.co",))
    http.routes["/events"] = ok({"id": "created-1"})
    assert provider.create_event(new) == "created-1"
    provider.update_event("g1", new)
    assert [c["method"] for c in http.calls[1:]] == ["POST", "PATCH"] and http.calls[2]["url"].endswith("/events/g1")


# --- API ------------------------------------------------------------------------------------------------------


@pytest.fixture
def api(session: Session) -> Generator[tuple[TestClient, dict[str, str], FixtureEmailProvider, FixtureCalendarProvider]]:
    w = world(session)
    email = FixtureEmailProvider([msg("m1", "hr@contoso.com", "Interview invitation", "We would like to schedule an interview", "t1", datetime.now(UTC))])
    calendar = FixtureCalendarProvider()
    app = create_app()

    def accounts() -> AccountService:
        return AccountService(session, settings(), RecordingHttp({}), email_provider=email, calendar_provider=calendar)

    for dep in (get_session, profiles_session, tracking_session):
        app.dependency_overrides[dep] = lambda: session
    app.dependency_overrides[get_accounts] = accounts
    yield TestClient(app), w, email, calendar


def test_api_email_flow_and_no_send_endpoint(api: tuple[TestClient, dict[str, str], Any, Any]) -> None:
    client, w, _, _ = api
    base = f"/api/v1/profiles/{w['a']}/email"
    sync = client.post(f"{base}/sync").json()
    assert (sync["linked"], sync["scanned"]) == (1, 1)
    (link,) = client.get(f"{base}/links").json()
    assert link["classification"] == "interview_request" and link["application_id"] == w["app_a"]
    assert "subject" not in link and "snippet" not in link
    draft = client.post(f"{base}/links/{link['id']}/draft")
    assert draft.status_code == 201 and DRAFT_NOTICE in draft.json()["body"]
    assert client.post(f"{base}/links/{link['id']}/confirm").json()["status"] == "CONFIRMED"
    assert client.get(f"/api/v1/profiles/{w['b']}/email/links").json() == []
    assert client.post(f"/api/v1/profiles/{w['b']}/email/links/{link['id']}/draft").status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("send" in p.lower() for p in paths)  # there is no send endpoint at all


def test_api_calendar_approval_flow(api: tuple[TestClient, dict[str, str], Any, FixtureCalendarProvider]) -> None:
    client, w, _, calendar = api
    interview = client.post(f"/api/v1/profiles/{w['a']}/interviews", json={"application_id": w["app_a"], "scheduled_at": (NOW + timedelta(days=2)).isoformat(), "type": "coding"}).json()
    base = f"/api/v1/profiles/{w['a']}/calendar"
    request = client.post(f"{base}/requests", json={"interview_id": interview["id"]})
    assert request.status_code == 201 and request.json()["status"] == "PENDING" and calendar.created == []
    assert len(client.get(f"{base}/requests", params={"status_": "PENDING"}).json()) in (0, 1)
    approved = client.post(f"{base}/requests/{request.json()['id']}/approve")
    assert approved.status_code == 200 and approved.json()["status"] == "DONE" and len(calendar.created) == 1
    assert client.post(f"{base}/requests/{request.json()['id']}/approve").status_code == 422  # not twice
    assert client.post(f"/api/v1/profiles/{w['b']}/calendar/requests/{request.json()['id']}/approve").status_code == 404


def test_api_integrations_status_hides_tokens_and_demo_blocks_connect(session: Session) -> None:
    w = world(session)
    app = create_app()
    for dep in (get_session, profiles_session):
        app.dependency_overrides[dep] = lambda: session
    app.dependency_overrides[get_accounts] = lambda: AccountService(session, settings(demo_mode=True), RecordingHttp({}))
    client = TestClient(app)
    status = client.get(f"/api/v1/profiles/{w['a']}/integrations")
    assert status.status_code == 200 and [s["connected"] for s in status.json()] == [False, False]
    blocked = client.post(f"/api/v1/profiles/{w['a']}/integrations/email/connect")
    assert blocked.status_code == 422 and "demo mode" in blocked.text
    assert client.get("/api/v1/integrations/google/callback", params={"state": "nope", "code": "x"}).status_code == 422
    assert client.get("/api/v1/profiles/nope/integrations").status_code == 404
