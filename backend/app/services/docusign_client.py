"""
DocuSign client — JWT Grant (impersonation) auth + in-process token cache.

Foundation for Phase 9 contract signing (Task 9.3a). This layer is
decision-independent: it doesn't care who signs or what the document is — it
just hands the rest of Phase 9 an authenticated `ApiClient` to build on.

Provider abstraction mirrors EmailService (`EMAIL_PROVIDER`):
  - DOCUSIGN_PROVIDER=mock     → synthetic token, no network (safe default;
                                 unit tests / local dev run without consent or creds).
  - DOCUSIGN_PROVIDER=sandbox  → real JWT user-token mint against the developer sandbox.

JWT Grant is deliberate (not Authorization Code): BluOnX is an unattended service
integration — envelopes are sent by backend automation with no human at a consent
screen. Tokens are 1-hour with NO refresh token, so the client caches in-process
(single-Fargate-task, no Redis) and re-mints on demand with a safety margin. No
token is ever persisted. On the first mint the impersonated user must grant consent
once; the SDK raises `consent_required` and we surface the one-time consent URL.

Two hosts, never conflated:
  - OAuth host (token mint + consent): DOCUSIGN_OAUTH_BASE_URL (e.g. account-d.docusign.com)
  - REST base (API calls):             {DOCUSIGN_ACCOUNT_BASE_URL}/restapi
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import quote
from uuid import uuid4

from fastapi.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Re-mint this many seconds before the token actually expires, so an in-flight
# request never races a hard expiry.
_SAFETY_MARGIN_SECONDS = 60


# ── Data classes / errors ─────────────────────────────────────────────────────


@dataclass
class MintedToken:
    access_token: str
    expires_in: int  # seconds until expiry, as reported by the issuer


class DocuSignConsentRequired(Exception):
    """Raised when the impersonated user has not yet granted consent.

    Carries the one-time consent URL the user visits once in a browser.
    """

    def __init__(self, consent_url: str) -> None:
        super().__init__(
            "DocuSign consent required — visit the consent URL once as the "
            "impersonated user, then retry."
        )
        self.consent_url = consent_url


# ── Consent URL (pure, independently testable) ────────────────────────────────


def build_consent_url(
    *, oauth_base: str, integration_key: str, redirect_uri: str, scopes: str
) -> str:
    """Construct the one-time JWT-consent grant URL.

    The caller visits this once in a browser as the impersonated user and clicks
    *allow*; the returned `code` is ignored. Consent then persists server-side
    until revoked.
    """
    return (
        f"https://{oauth_base}/oauth/auth"
        f"?response_type=code"
        f"&scope={quote(scopes)}"
        f"&client_id={quote(integration_key)}"
        f"&redirect_uri={quote(redirect_uri, safe='')}"
    )


# ── Provider protocol + implementations ───────────────────────────────────────


@runtime_checkable
class DocuSignAuthProvider(Protocol):
    def mint(self) -> MintedToken:
        """Mint a fresh user access token. Synchronous (SDK blocks under the hood)."""
        ...


class MockDocuSignAuthProvider:
    """Synthetic-token provider — no network call.

    Lets unit tests and local dev run without consent or creds, the same role
    MockEmailProvider plays for email.
    """

    def mint(self) -> MintedToken:
        token = f"mock-{uuid4()}"
        logger.info("[MOCK DOCUSIGN] minted synthetic token %s", token)
        return MintedToken(
            access_token=token,
            expires_in=settings.DOCUSIGN_TOKEN_EXPIRES_IN,
        )


class SandboxDocuSignAuthProvider:
    """Real JWT user-token mint against the DocuSign developer sandbox."""

    def __init__(self) -> None:
        # Fail fast (mirrors create_email_provider's SES guard) — surfaces a
        # misconfiguration as a clear RuntimeError, not a deep SDK error.
        missing = [
            name
            for name in (
                "DOCUSIGN_INTEGRATION_KEY",
                "DOCUSIGN_USER_ID",
                "DOCUSIGN_PRIVATE_KEY_PATH",
            )
            if not getattr(settings, name)
        ]
        if missing:
            raise RuntimeError(
                "DOCUSIGN_PROVIDER=sandbox requires "
                + ", ".join(missing)
                + " to be set in environment / .env"
            )

    def mint(self) -> MintedToken:
        # Imported lazily so importing this module (and the mock path) never
        # requires the SDK to be importable at collection time.
        from docusign_esign import ApiClient, ApiException

        private_key_bytes = Path(settings.DOCUSIGN_PRIVATE_KEY_PATH).read_bytes()
        scopes = settings.DOCUSIGN_JWT_SCOPES.split()

        api_client = ApiClient()
        api_client.set_oauth_host_name(settings.DOCUSIGN_OAUTH_BASE_URL)

        try:
            token = api_client.request_jwt_user_token(
                client_id=settings.DOCUSIGN_INTEGRATION_KEY,
                user_id=settings.DOCUSIGN_USER_ID,
                oauth_host_name=settings.DOCUSIGN_OAUTH_BASE_URL,
                private_key_bytes=private_key_bytes,
                expires_in=settings.DOCUSIGN_TOKEN_EXPIRES_IN,
                scopes=scopes,
            )
        except ApiException as exc:
            body = exc.body or b""
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")
            if "consent_required" in body:
                raise DocuSignConsentRequired(
                    consent_url=build_consent_url(
                        oauth_base=settings.DOCUSIGN_OAUTH_BASE_URL,
                        integration_key=settings.DOCUSIGN_INTEGRATION_KEY,
                        redirect_uri=settings.DOCUSIGN_REDIRECT_URI,
                        scopes=settings.DOCUSIGN_JWT_SCOPES,
                    )
                ) from exc
            raise

        return MintedToken(
            access_token=token.access_token,
            expires_in=int(token.expires_in),
        )


def create_docusign_provider() -> DocuSignAuthProvider:
    """Select the auth provider from DOCUSIGN_PROVIDER (mirrors create_email_provider)."""
    if settings.DOCUSIGN_PROVIDER == "sandbox":
        return SandboxDocuSignAuthProvider()
    return MockDocuSignAuthProvider()


# ── Client (token cache + threadpool wrapper) ─────────────────────────────────


class DocuSignClient:
    """Holds the in-process token cache and the authenticated-client factory.

    The blocking SDK mint runs in a threadpool so it never blocks the event loop.
    A lock serialises concurrent mints so a burst of first requests mints once.
    """

    def __init__(
        self,
        provider: DocuSignAuthProvider,
        *,
        safety_margin_seconds: int = _SAFETY_MARGIN_SECONDS,
    ) -> None:
        self._provider = provider
        self._safety_margin = safety_margin_seconds
        self._token: str | None = None
        self._expires_at: datetime | None = None
        self._lock = asyncio.Lock()

    def _is_fresh(self) -> bool:
        if self._token is None or self._expires_at is None:
            return False
        cutoff = self._expires_at - timedelta(seconds=self._safety_margin)
        return datetime.now(timezone.utc) < cutoff

    async def get_access_token(self, force: bool = False) -> str:
        """Return a valid access token, minting/re-minting as needed.

        Raises DocuSignConsentRequired (from the sandbox provider) if the
        impersonated user has not granted consent yet.
        """
        if not force and self._is_fresh():
            return self._token  # type: ignore[return-value]

        async with self._lock:
            # Re-check inside the lock — another coroutine may have just minted.
            if not force and self._is_fresh():
                return self._token  # type: ignore[return-value]

            minted = await run_in_threadpool(self._provider.mint)
            self._token = minted.access_token
            self._expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=minted.expires_in
            )
            logger.info("DocuSign token minted; expires_at=%s", self._expires_at.isoformat())
            return self._token

    async def get_api_client(self):
        """Build an authenticated `docusign_esign.ApiClient` for 9.3b.

        Host = the REST base ({DOCUSIGN_ACCOUNT_BASE_URL}/restapi); bearer token
        set as the default auth header. Distinct from the OAuth host used to mint.
        """
        from docusign_esign import ApiClient

        token = await self.get_access_token()
        api_client = ApiClient()
        if settings.DOCUSIGN_ACCOUNT_BASE_URL:
            api_client.host = f"{settings.DOCUSIGN_ACCOUNT_BASE_URL}/restapi"
        api_client.set_default_header("Authorization", f"Bearer {token}")
        return api_client


# ── Process-wide singleton ────────────────────────────────────────────────────
#
# Unlike EmailService (per-request), the token cache must persist across
# requests, so the client is a module-level singleton. Doubles as a FastAPI
# dependency so routes/tests can inject or override it.

_client_singleton: DocuSignClient | None = None


def get_docusign_client() -> DocuSignClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = DocuSignClient(provider=create_docusign_provider())
    return _client_singleton
