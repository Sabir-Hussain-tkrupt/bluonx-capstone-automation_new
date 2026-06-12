"""
Application settings loaded from environment variables.

Uses pydantic-settings v2 with model_config (not class Config).
"""

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

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # Google Maps
    GOOGLE_MAPS_API_KEY: str | None = None

    # AWS
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str = "us-east-1"

    # Email
    EMAIL_PROVIDER: str = "ses"  # "mock" or "ses"
    # SES_FROM_EMAIL: str = "awaisonfreelance@gmail.com"
    SES_FROM_EMAIL: str = "noreply@bluonx.com"

    # Portal (vendor-facing URL for magic links)
    PORTAL_BASE_URL: str = "http://localhost:5173"

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


settings = Settings()
