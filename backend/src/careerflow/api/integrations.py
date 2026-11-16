from collections.abc import Generator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from careerflow.application.integrations.accounts import AccountService
from careerflow.application.integrations.calendar_service import CalendarService
from careerflow.application.integrations.email_service import EmailService
from careerflow.application.profiles.service import ProfileItemNotFoundError, ProfileNotFoundError
from careerflow.demo import ExternalWritesDisabledError
from careerflow.domain.integrations.ports import IntegrationError, NotConnectedError
from careerflow.infrastructure.database.session import create_database_engine
from careerflow.settings import get_settings

router = APIRouter(tags=["integrations"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


def get_accounts(session: Session = Depends(get_session)) -> AccountService:
    """Overridden in tests to inject offline providers."""
    return AccountService(session, get_settings())


class AccountOutput(BaseModel):
    kind: str
    connected: bool
    provider: str | None
    scopes: list[str]
    allow_writes: bool
    last_synced_at: datetime | None


class ConnectInput(BaseModel):
    allow_writes: bool = False


class ConnectOutput(BaseModel):
    authorization_url: str


class LinkOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    application_id: str | None
    message_id: str
    thread_id: str | None
    sender_domain: str | None
    classification: str
    score: float
    reasons: list[str]
    received_at: datetime
    status: str


class ConfirmInput(BaseModel):
    application_id: str | None = None


class DraftOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    link_id: str
    body: str
    created_at: datetime


class SyncOutput(BaseModel):
    scanned: int
    linked: int
    unmatched: int
    skipped_known: int


class ImportOutput(BaseModel):
    scanned: int
    created: int
    updated: int
    unchanged: int
    unmatched: int
    reminders: int


class RequestInput(BaseModel):
    interview_id: str


class RequestOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    interview_id: str | None
    action: str
    event_id: str | None
    payload_json: dict[str, Any]
    status: str
    error: str | None = Field(default=None)
    created_at: datetime
    decided_at: datetime | None


def _fail(error: Exception) -> HTTPException:
    if isinstance(error, ProfileNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="profile not found")
    if isinstance(error, ProfileItemNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="record not found")
    if isinstance(error, NotConnectedError):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, ExternalWritesDisabledError):
        return HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error))
    if isinstance(error, IntegrationError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


_ERRORS = (ProfileNotFoundError, ProfileItemNotFoundError, IntegrationError, ExternalWritesDisabledError, ValueError)


@router.get("/profiles/{profile_id}/integrations", response_model=list[AccountOutput])
def integrations(profile_id: str, accounts: AccountService = Depends(get_accounts)) -> list[AccountOutput]:
    """Which accounts are connected. Never returns tokens."""
    try:
        return [
            AccountOutput(kind=a.kind, connected=a.connected, provider=a.provider, scopes=list(a.scopes), allow_writes=a.allow_writes, last_synced_at=a.last_synced_at)
            for a in accounts.status(profile_id)
        ]
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/integrations/{kind}/connect", response_model=ConnectOutput)
def connect(profile_id: str, kind: str, payload: ConnectInput | None = None, accounts: AccountService = Depends(get_accounts)) -> ConnectOutput:
    try:
        return ConnectOutput(authorization_url=accounts.start(profile_id, kind, (payload or ConnectInput()).allow_writes))
    except _ERRORS as error:
        raise _fail(error) from error


@router.get("/integrations/google/callback", response_model=AccountOutput)
def callback(state: str, code: str, accounts: AccountService = Depends(get_accounts)) -> AccountOutput:
    """OAuth redirect target. Tokens are stored encrypted; the response only says what connected."""
    try:
        account = accounts.complete(state, code)
    except _ERRORS as error:
        raise _fail(error) from error
    return AccountOutput(kind=account.kind, connected=True, provider=account.provider, scopes=list(account.scopes), allow_writes=account.allow_writes, last_synced_at=None)


@router.delete("/profiles/{profile_id}/integrations/{kind}", status_code=204)
def disconnect(profile_id: str, kind: str, accounts: AccountService = Depends(get_accounts)) -> None:
    try:
        accounts.disconnect(profile_id, kind)
    except _ERRORS as error:
        raise _fail(error) from error


# -- email (read-only; drafts stay local) -------------------------------------------------------------


@router.post("/profiles/{profile_id}/email/sync", response_model=SyncOutput)
def sync_email(profile_id: str, session: Session = Depends(get_session), accounts: AccountService = Depends(get_accounts)) -> SyncOutput:
    try:
        provider = accounts.email_provider(profile_id)
        result = EmailService(session).sync(profile_id, provider)
        accounts.mark_synced(profile_id, "email")
    except _ERRORS as error:
        raise _fail(error) from error
    return SyncOutput(**vars(result))


@router.get("/profiles/{profile_id}/email/links", response_model=list[LinkOutput])
def list_links(profile_id: str, status_: str | None = None, session: Session = Depends(get_session)) -> list[LinkOutput]:
    try:
        return [LinkOutput.model_validate(row) for row in EmailService(session).list_links(profile_id, status_)]
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/email/links/{link_id}/confirm", response_model=LinkOutput)
def confirm_link(profile_id: str, link_id: str, payload: ConfirmInput | None = None, session: Session = Depends(get_session)) -> LinkOutput:
    try:
        return LinkOutput.model_validate(EmailService(session).confirm(profile_id, link_id, (payload or ConfirmInput()).application_id))
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/email/links/{link_id}/dismiss", response_model=LinkOutput)
def dismiss_link(profile_id: str, link_id: str, session: Session = Depends(get_session)) -> LinkOutput:
    try:
        return LinkOutput.model_validate(EmailService(session).dismiss(profile_id, link_id))
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/email/links/{link_id}/draft", response_model=DraftOutput, status_code=201)
def draft_reply(profile_id: str, link_id: str, session: Session = Depends(get_session)) -> DraftOutput:
    """Create a local reply draft for the user to copy and send themselves. Nothing is sent."""
    try:
        return DraftOutput.model_validate(EmailService(session).draft_reply(profile_id, link_id))
    except _ERRORS as error:
        raise _fail(error) from error


@router.get("/profiles/{profile_id}/email/links/{link_id}/drafts", response_model=list[DraftOutput])
def list_drafts(profile_id: str, link_id: str, session: Session = Depends(get_session)) -> list[DraftOutput]:
    try:
        return [DraftOutput.model_validate(d) for d in EmailService(session).drafts(profile_id, link_id)]
    except _ERRORS as error:
        raise _fail(error) from error


# -- calendar --------------------------------------------------------------------------------------------


def _calendar(session: Session, accounts: AccountService) -> CalendarService:
    return CalendarService(session, get_settings(), accounts)


@router.post("/profiles/{profile_id}/calendar/import", response_model=ImportOutput)
def import_events(profile_id: str, session: Session = Depends(get_session), accounts: AccountService = Depends(get_accounts)) -> ImportOutput:
    try:
        provider = accounts.calendar_provider(profile_id)
        result = _calendar(session, accounts).import_events(profile_id, provider)
    except _ERRORS as error:
        raise _fail(error) from error
    return ImportOutput(**vars(result))


@router.post("/profiles/{profile_id}/calendar/requests", response_model=RequestOutput, status_code=201)
def propose_event(profile_id: str, payload: RequestInput, session: Session = Depends(get_session), accounts: AccountService = Depends(get_accounts)) -> RequestOutput:
    """Propose a calendar change. Nothing is written until it is approved."""
    try:
        return RequestOutput.model_validate(_calendar(session, accounts).propose(profile_id, payload.interview_id))
    except _ERRORS as error:
        raise _fail(error) from error


@router.get("/profiles/{profile_id}/calendar/requests", response_model=list[RequestOutput])
def list_requests(profile_id: str, status_: str | None = None, session: Session = Depends(get_session), accounts: AccountService = Depends(get_accounts)) -> list[RequestOutput]:
    try:
        return [RequestOutput.model_validate(r) for r in _calendar(session, accounts).requests(profile_id, status_)]
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/calendar/requests/{request_id}/approve", response_model=RequestOutput)
def approve_request(profile_id: str, request_id: str, session: Session = Depends(get_session), accounts: AccountService = Depends(get_accounts)) -> RequestOutput:
    """Explicit user approval: the only action that writes to the external calendar."""
    try:
        provider = accounts.calendar_provider(profile_id)
        row = _calendar(session, accounts).approve(profile_id, request_id, provider, accounts.calendar_allows_writes(profile_id))
    except _ERRORS as error:
        raise _fail(error) from error
    return RequestOutput.model_validate(row)


@router.post("/profiles/{profile_id}/calendar/requests/{request_id}/reject", response_model=RequestOutput)
def reject_request(profile_id: str, request_id: str, session: Session = Depends(get_session), accounts: AccountService = Depends(get_accounts)) -> RequestOutput:
    try:
        return RequestOutput.model_validate(_calendar(session, accounts).reject(profile_id, request_id))
    except _ERRORS as error:
        raise _fail(error) from error
