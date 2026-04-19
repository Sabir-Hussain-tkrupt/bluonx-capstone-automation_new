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
    SES_FROM_EMAIL: str = "awaisonfreelance@gmail.com"

    # Portal (vendor-facing URL for magic links)
    PORTAL_BASE_URL: str = "http://localhost:5173"

    # Vendor portal auth (Phase 5) — MUST differ from SUPABASE_JWT_SECRET.
    # Custom HS256 JWT signed server-side after magic link validation.
    VENDOR_JWT_SECRET: str
    VENDOR_JWT_EXPIRY_HOURS: int = 4


settings = Settings()
