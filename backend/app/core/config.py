"""
Application settings loaded from environment variables.

Uses pydantic-settings v2 with model_config (not class Config).
"""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str

    # App
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Scheduling anchor. The single business timezone for "today" decisions
    # (milestone actual dates now; the 10.3 daily check-in job later). Kept here
    # so the whole system shares one clock. See app/core/time.py::business_today.
    BUSINESS_TIMEZONE: str = "America/Chicago"

    # CORS
    # Browser origins allowed to call this API. The localhost default is a dev
    # convenience; production must supply real https origins (enforced in
    # _validate_cors_origins below) so a deploy that forgets this var fails at
    # startup rather than at the first browser call.
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # Logging
    # LOG_LEVEL is the root logger level. LOG_FORMAT selects the handler
    # formatter: "console" (human-readable, for local dev) or "json" (one JSON
    # object per line, for CloudWatch Logs Insights). Left unset, LOG_FORMAT
    # resolves to "json" under APP_ENV=production and "console" otherwise, so a
    # production deploy gets structured logs without anyone remembering to set
    # it. See app/core/logging_config.py.
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str | None = None

    # Google Maps
    GOOGLE_MAPS_API_KEY: str | None = None

    # AWS
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str = "us-east-1"

    # Email
    # Safe default: "mock" sends no real email. Set EMAIL_PROVIDER=ses (with AWS
    # creds + a verified SES_FROM_EMAIL) to send real email. Production is
    # required to use "ses" (enforced in _validate_email_provider below).
    EMAIL_PROVIDER: str = "mock"  # "mock" or "ses"
    SES_FROM_EMAIL: str = "noreply@bluonx.com"
    # SES configuration set name. When set, sends carry ConfigurationSetName so
    # SES emits Delivery/Bounce/Complaint events to SNS. Empty/None → no event
    # tracking (behaves as before). Must name an existing config set or sends fail.
    SES_CONFIGURATION_SET: str | None = None  # e.g. "bluonx-dev"

    # Portal (vendor-facing URL for magic links)
    PORTAL_BASE_URL: str = "http://localhost:5173"

    # Staff/admin frontend base URL. Used to build the Supabase invite email
    # redirect (`{FRONTEND_BASE_URL}/accept-invite`) so an invited admin/PM lands
    # on our set-password page. Distinct from PORTAL_BASE_URL (vendor portal).
    # Production must set a non-localhost https URL (enforced below) and the same
    # URL must be on Supabase Auth's redirect allow list.
    FRONTEND_BASE_URL: str = "http://localhost:5173"

    # Vendor portal auth (Phase 5) — MUST differ from SUPABASE_JWT_SECRET.
    # Custom HS256 JWT signed server-side after magic link validation.
    VENDOR_JWT_SECRET: str
    VENDOR_JWT_EXPIRY_HOURS: int = 4

    # DocuSign (Phase 9 — JWT Grant impersonation auth).
    # Provider toggle mirrors EMAIL_PROVIDER: "mock" (synthetic token, no
    # network — safe default when creds/consent aren't in place) or "sandbox"
    # (real JWT mint against the developer sandbox).
    DOCUSIGN_PROVIDER: str = "mock"  # "mock" or "sandbox"
    # Account/credential keys (live in .env; optional so mock/dev loads cleanly).
    DOCUSIGN_ACCOUNT_ID: str | None = None
    DOCUSIGN_USER_ID: str | None = None  # impersonated system user (JWT `sub`)
    DOCUSIGN_INTEGRATION_KEY: str | None = None  # OAuth client_id
    DOCUSIGN_PRIVATE_KEY_PATH: str | None = None  # RSA key (.pem) under backend/secrets/
    # REST base host for API calls, e.g. https://demo.docusign.net.
    # Kept DISTINCT from the OAuth host below — do not conflate the two.
    DOCUSIGN_ACCOUNT_BASE_URL: str | None = None
    # OAuth host for token mint + consent (sandbox constant). No scheme.
    DOCUSIGN_OAUTH_BASE_URL: str = "account-d.docusign.com"
    DOCUSIGN_JWT_SCOPES: str = "signature impersonation"
    # Any URI registered on the integration key — used only to build the
    # one-time consent URL (the returned code is ignored).
    DOCUSIGN_REDIRECT_URI: str = "http://localhost:8000/api/v1/admin/docusign-health"
    DOCUSIGN_TOKEN_EXPIRES_IN: int = 3600  # JWT assertion lifetime (seconds)

    # DocuSign Connect status webhook (Task 9.3b).
    # HMAC key mirrors the key configured in DocuSign admin (Connect → HMAC);
    # the webhook verifies the raw request body against it. None ⇒ verification
    # rejects every request (fail-closed) until the key is configured.
    DOCUSIGN_CONNECT_HMAC_KEY: str | None = None
    # Public URL placed in each envelope's eventNotification so Connect can
    # reach us (an ngrok tunnel in dev). None ⇒ no eventNotification attached.
    DOCUSIGN_CONNECT_WEBHOOK_URL: str | None = None

    # Internal BluOnX signer (routingOrder 1 — signs first) for the contract
    # envelope. Pure config (decision 3b) — sandbox = your own name/email.
    CONTRACT_OWNER_SIGNER_NAME: str | None = None
    CONTRACT_OWNER_SIGNER_EMAIL: str | None = None

    # Firm contact-information block on the contract PDF. Name defaults
    # to the legal entity; the rest are optional and render only when set (supply
    # real values via env). Kept as pure config so the boilerplate is a one-place
    # swap, mirroring CONTRACT_OWNER_SIGNER_*.
    CONTRACT_FIRM_NAME: str = "BluOnX Development LLC"
    CONTRACT_FIRM_CONTACT_EMAIL: str | None = None
    CONTRACT_FIRM_CONTACT_PHONE: str | None = None
    CONTRACT_FIRM_CONTACT_ADDRESS: str | None = None

    @model_validator(mode="after")
    def _validate_email_provider(self) -> "Settings":
        """Fail fast on unsafe / incomplete email configuration at load time.

        - Production must use the real provider, never the mock, so a
          misconfigured deploy cannot silently drop every email.
        - Selecting "ses" requires AWS credentials, surfaced at startup
          instead of lazily on the first send.
        """
        if self.APP_ENV.lower() == "production" and self.EMAIL_PROVIDER != "ses":
            raise ValueError(
                "EMAIL_PROVIDER must be 'ses' when APP_ENV=production "
                f"(got '{self.EMAIL_PROVIDER}'); refusing to start so emails "
                "are not silently dropped."
            )
        if self.EMAIL_PROVIDER == "ses" and not (
            self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY
        ):
            raise ValueError(
                "EMAIL_PROVIDER=ses requires AWS_ACCESS_KEY_ID and "
                "AWS_SECRET_ACCESS_KEY to be set."
            )
        return self

    @model_validator(mode="after")
    def _validate_frontend_base_url(self) -> "Settings":
        """Fail fast on an unsafe staff-frontend URL in production.

        Invite emails redirect to `{FRONTEND_BASE_URL}/accept-invite`. In
        production the localhost dev default would send invited users to a page
        that does not exist, so require a real https origin. Also mirrors the
        Supabase redirect allow list, which rejects non-https/localhost origins.
        """
        if self.APP_ENV.lower() == "production":
            url = self.FRONTEND_BASE_URL.strip()
            if not url.startswith("https://") or "localhost" in url or "127.0.0.1" in url:
                raise ValueError(
                    "FRONTEND_BASE_URL must be a non-localhost https URL when "
                    f"APP_ENV=production (got '{self.FRONTEND_BASE_URL}'); refusing "
                    "to start so invite links do not point at a dev host."
                )
        return self

    @model_validator(mode="after")
    def _validate_cors_origins(self) -> "Settings":
        """Fail fast on unsafe CORS origins in production.

        Without this, a deploy that forgets CORS_ORIGINS boots cleanly and then
        fails every browser call with an opaque CORS error that looks like a
        frontend bug. Mirrors _validate_frontend_base_url: refuse to start so the
        misconfiguration surfaces at deploy time.
        """
        if self.APP_ENV.lower() != "production":
            return self

        if not self.CORS_ORIGINS:
            raise ValueError(
                "CORS_ORIGINS must list at least one origin when "
                "APP_ENV=production; refusing to start so the frontend does not "
                "fail every request with an opaque CORS error."
            )

        for origin in self.CORS_ORIGINS:
            value = origin.strip()
            if value == "*":
                raise ValueError(
                    "CORS_ORIGINS must not contain '*' when APP_ENV=production; "
                    "name the exact frontend origin(s) instead."
                )
            if "localhost" in value or "127.0.0.1" in value:
                raise ValueError(
                    f"CORS_ORIGINS contains a localhost origin ('{origin}') while "
                    "APP_ENV=production; refusing to start so a dev origin is not "
                    "trusted in production."
                )
            if not value.startswith("https://"):
                raise ValueError(
                    f"CORS_ORIGINS entry '{origin}' must be an https:// origin when "
                    "APP_ENV=production."
                )
        return self

    @model_validator(mode="after")
    def _resolve_log_format(self) -> "Settings":
        """Default LOG_FORMAT from APP_ENV, then validate the logging knobs.

        Deriving the default means production gets JSON logs without a separate
        env var to forget; an explicit LOG_FORMAT still wins.
        """
        if self.LOG_FORMAT is None:
            self.LOG_FORMAT = "json" if self.APP_ENV.lower() == "production" else "console"

        self.LOG_FORMAT = self.LOG_FORMAT.strip().lower()
        if self.LOG_FORMAT not in ("console", "json"):
            raise ValueError(
                f"LOG_FORMAT must be 'console' or 'json' (got '{self.LOG_FORMAT}')."
            )

        self.LOG_LEVEL = self.LOG_LEVEL.strip().upper()
        if self.LOG_LEVEL not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError(
                "LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL "
                f"(got '{self.LOG_LEVEL}')."
            )
        return self


settings = Settings()
