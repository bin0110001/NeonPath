"""Connected accounts: OAuth flow, encrypted token storage, provider construction.

Tokens never leave this module in plaintext: they are encrypted in the database, decrypted
only to call the provider, and the API reports only whether an account is connected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.profiles.service import ProfileService
from careerflow.domain.integrations.ports import (
    CalendarProvider,
    EmailProvider,
    IntegrationError,
    NotConnectedError,
)
from careerflow.infrastructure.database.models import IntegrationAccountModel, OAuthStateModel
from careerflow.infrastructure.integrations.google import (
    CALENDAR_READ_SCOPES,
    CALENDAR_WRITE_SCOPES,
    GMAIL_SCOPES,
    GmailProvider,
    GoogleCalendarProvider,
    GoogleOAuth,
    new_pkce,
)
from careerflow.infrastructure.integrations.http import HttpxIntegrationClient, IntegrationHttp
from careerflow.infrastructure.security.crypto import TokenCipher
from careerflow.settings import Settings, get_settings

KINDS = ("email", "calendar")
STATE_TTL = timedelta(minutes=15)
REFRESH_MARGIN = timedelta(seconds=60)


@dataclass
class AccountStatus:
    kind: str
    connected: bool
    provider: str | None = None
    scopes: tuple[str, ...] = ()
    allow_writes: bool = False
    last_synced_at: datetime | None = None


def ensure_integrations_allowed(settings: Settings) -> None:
    """Real mailbox/calendar connections are never made from a demo installation."""
    if settings.demo_mode:
        raise IntegrationError("integrations with real accounts are disabled in demo mode")


class AccountService:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        http: IntegrationHttp | None = None,
        email_provider: EmailProvider | None = None,
        calendar_provider: CalendarProvider | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.http = http or HttpxIntegrationClient()
        self._email_override, self._calendar_override = email_provider, calendar_provider
        self.clock = clock
        self.profiles = ProfileService(session)

    # -- helpers -----------------------------------------------------------------------------

    def _cipher(self) -> TokenCipher:
        return TokenCipher(self.settings.integration_encryption_key)

    def _oauth(self) -> GoogleOAuth:
        s = self.settings
        return GoogleOAuth(s.google_client_id, s.google_client_secret, s.oauth_redirect_uri, self.http)

    def _account(self, profile_id: str, kind: str) -> IntegrationAccountModel | None:
        return self.session.scalars(
            select(IntegrationAccountModel).where(
                IntegrationAccountModel.profile_id == profile_id, IntegrationAccountModel.kind == kind
            )
        ).first()

    @staticmethod
    def _scopes(kind: str, allow_writes: bool) -> tuple[str, ...]:
        if kind == "email":
            return GMAIL_SCOPES  # read-only, always
        return CALENDAR_WRITE_SCOPES if allow_writes else CALENDAR_READ_SCOPES

    # -- connect / disconnect -----------------------------------------------------------------

    def start(self, profile_id: str, kind: str, allow_writes: bool = False) -> str:
        """Begin the OAuth flow; returns the URL the user must visit."""
        ensure_integrations_allowed(self.settings)
        if kind not in KINDS:
            raise IntegrationError(f"kind must be one of {KINDS}")
        if allow_writes and kind != "calendar":
            raise IntegrationError("only calendar connections can request write access")
        self.profiles.get_profile(profile_id)
        cipher, oauth = self._cipher(), self._oauth()
        from secrets import token_urlsafe

        state = token_urlsafe(24)
        verifier, challenge = new_pkce()
        self.session.add(
            OAuthStateModel(
                state=state, profile_id=profile_id, kind=kind, enc_verifier=cipher.encrypt(verifier),
                allow_writes=allow_writes, created_at=self.clock(),
            )  # fmt: skip
        )
        self.session.commit()
        return oauth.authorization_url(state, challenge, self._scopes(kind, allow_writes))

    def complete(self, state: str, code: str) -> IntegrationAccountModel:
        ensure_integrations_allowed(self.settings)
        pending = self.session.get(OAuthStateModel, state)
        if pending is None:
            raise IntegrationError("unknown or already used authorisation state")
        created = pending.created_at if pending.created_at.tzinfo else pending.created_at.replace(tzinfo=UTC)
        profile_id, kind, writes = pending.profile_id, pending.kind, pending.allow_writes
        cipher = self._cipher()
        verifier = cipher.decrypt(pending.enc_verifier)
        self.session.delete(pending)  # single use, even if the exchange fails
        self.session.commit()
        if self.clock() - created > STATE_TTL:
            raise IntegrationError("authorisation expired; start again")
        tokens = self._oauth().exchange_code(code, verifier)
        account = self._account(profile_id, kind) or IntegrationAccountModel(profile_id=profile_id, kind=kind, provider="google")
        account.enc_access_token = cipher.encrypt(str(tokens["access_token"]))
        if tokens.get("refresh_token"):
            account.enc_refresh_token = cipher.encrypt(str(tokens["refresh_token"]))
        account.expires_at = self.clock() + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        account.scopes = list(self._scopes(kind, writes))
        account.allow_writes = writes
        self.session.add(account)
        self.session.commit()
        return account

    def disconnect(self, profile_id: str, kind: str) -> None:
        self.profiles.get_profile(profile_id)
        account = self._account(profile_id, kind)
        if account is not None:
            self.session.delete(account)
            self.session.commit()

    def status(self, profile_id: str) -> list[AccountStatus]:
        self.profiles.get_profile(profile_id)
        out = []
        for kind in KINDS:
            account = self._account(profile_id, kind)
            out.append(
                AccountStatus(kind, False)
                if account is None
                else AccountStatus(kind, True, account.provider, tuple(account.scopes), account.allow_writes, account.last_synced_at)
            )
        return out

    # -- tokens & providers --------------------------------------------------------------------

    def _access_token(self, account: IntegrationAccountModel) -> str:
        cipher = self._cipher()
        expires = account.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires is None or expires - REFRESH_MARGIN > self.clock():
            return cipher.decrypt(account.enc_access_token)
        if not account.enc_refresh_token:
            raise NotConnectedError("the access token expired and there is no refresh token; reconnect the account")
        tokens = self._oauth().refresh(cipher.decrypt(account.enc_refresh_token))
        account.enc_access_token = cipher.encrypt(str(tokens["access_token"]))
        account.expires_at = self.clock() + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        self.session.commit()
        return str(tokens["access_token"])

    def email_provider(self, profile_id: str) -> EmailProvider:
        if self._email_override is not None:
            return self._email_override
        ensure_integrations_allowed(self.settings)
        account = self._account(profile_id, "email")
        if account is None:
            raise NotConnectedError("no email account is connected for this profile")
        return GmailProvider(self._access_token(account), self.http)

    def calendar_provider(self, profile_id: str) -> CalendarProvider:
        if self._calendar_override is not None:
            return self._calendar_override
        ensure_integrations_allowed(self.settings)
        account = self._account(profile_id, "calendar")
        if account is None:
            raise NotConnectedError("no calendar is connected for this profile")
        return GoogleCalendarProvider(self._access_token(account), self.http)

    def calendar_allows_writes(self, profile_id: str) -> bool:
        if self._calendar_override is not None:
            return True
        account = self._account(profile_id, "calendar")
        return bool(account and account.allow_writes)

    def mark_synced(self, profile_id: str, kind: str) -> None:
        account = self._account(profile_id, kind)
        if account is not None:
            account.last_synced_at = self.clock()
            self.session.commit()
