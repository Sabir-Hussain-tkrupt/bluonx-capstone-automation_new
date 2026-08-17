"""
BluOnX API — FastAPI application entry point.

Lifespan creates the global Supabase client.
CORS allows the frontend dev server.
All routers are mounted under /api/v1 (except /health).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.request_logging import RequestLoggingMiddleware
from app.core.supabase_client import init_supabase
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers import (
    awards,
    bid_invitations,
    bid_packages,
    bid_revisions,
    bid_submissions,
    bid_templates,
    contract_signers,
    contracts,
    docusign_health,
    docusign_webhooks,
    health,
    holidays,
    milestones,
    notifications,
    projects,
    reviews,
    scheduler_health,
    tasks,
    trades,
    users,
    vendor_auth,
    vendor_portal,
    vendors,
    webhooks,
)


# Install the root logging configuration before anything else logs, so lifespan
# and startup lines already carry the configured formatter.
configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create and store global Supabase client, then start the scheduler
    client = init_supabase(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    app.state.supabase = client
    # Make the active email mode unmissable in logs.
    if settings.EMAIL_PROVIDER == "ses":
        logger.info(
            "Email: SES provider active (from=%s, region=%s)",
            settings.SES_FROM_EMAIL,
            settings.AWS_REGION,
        )
    else:
        logger.warning(
            "Email: MOCK provider active (EMAIL_PROVIDER=%s), no real emails will be sent",
            settings.EMAIL_PROVIDER,
        )
    start_scheduler()
    yield
    # Shutdown: stop the scheduler (httpx client handles its own pool)
    stop_scheduler()


app = FastAPI(
    title="BluOnX Bid Management API",
    description="Backend API for BluOnX Bid Management & Vendor Coordination System",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS Middleware ───────────────────────────────────────────────────────
# allow_credentials is deliberately omitted: both auth paths are
# `Authorization: Bearer` (Supabase JWT for staff, custom JWT for vendors) and
# nothing sets or reads a cookie, so credentialed CORS is surface we don't use.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ── Request Logging Middleware ────────────────────────────────────────────
# Registered AFTER CORS on purpose: add_middleware() inserts at position 0, so
# the last one added is the OUTERMOST layer. Outermost is what we want — it
# times the full request including CORS handling, and assigns a correlation id
# to preflight and CORS-rejected requests too.
app.add_middleware(RequestLoggingMiddleware)

# ── Health (root-level, no prefix) ───────────────────────────────────────
app.include_router(health.router)

# ── API v1 Routers ───────────────────────────────────────────────────────
_v1 = settings.API_V1_PREFIX

app.include_router(users.router, prefix=_v1, tags=["Users"])
app.include_router(vendors.router, prefix=_v1, tags=["Vendors"])
app.include_router(projects.router, prefix=_v1, tags=["Projects"])
app.include_router(tasks.router, prefix=_v1, tags=["Tasks"])
app.include_router(trades.router, prefix=_v1, tags=["Trades"])
app.include_router(holidays.router, prefix=_v1, tags=["Holidays"])
app.include_router(bid_packages.router, prefix=_v1, tags=["Bid Packages"])
app.include_router(bid_templates.router, prefix=_v1, tags=["Bid Templates"])
app.include_router(bid_invitations.router, prefix=_v1, tags=["Bid Invitations"])
app.include_router(bid_revisions.router, prefix=_v1, tags=["Bid Revisions"])
app.include_router(bid_submissions.router, prefix=_v1, tags=["Bid Submissions"])
app.include_router(awards.router, prefix=_v1, tags=["Awards"])
app.include_router(contracts.router, prefix=_v1, tags=["Contracts"])
app.include_router(contract_signers.router, prefix=_v1, tags=["Contract Signers"])
app.include_router(reviews.router, prefix=_v1, tags=["Reviews"])
app.include_router(milestones.router, prefix=_v1, tags=["Milestones"])
app.include_router(notifications.router, prefix=_v1, tags=["Notifications"])
app.include_router(webhooks.router, prefix=_v1, tags=["Webhooks"])
app.include_router(docusign_webhooks.router, prefix=_v1, tags=["DocuSign Webhooks"])
app.include_router(scheduler_health.router, prefix=_v1, tags=["Scheduler"])
app.include_router(docusign_health.router, prefix=_v1, tags=["DocuSign"])
app.include_router(vendor_auth.router, prefix=_v1, tags=["Vendor Auth"])
app.include_router(vendor_portal.router, prefix=_v1, tags=["Vendor Portal"])
