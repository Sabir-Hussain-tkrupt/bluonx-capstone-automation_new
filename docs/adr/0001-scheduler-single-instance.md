# 1. Scheduler runs in-process via APScheduler on a single-instance deployment

Date: 2026-05-21

## Status

Accepted

## Context

The system needs background jobs. The first is auto-expiry of per-vendor bid
revision requests: when a vendor neither submits nor declines by the deadline, the
request must transition `pending` → `expired` and its magic-link token must be
revoked. Phase 10 will add more (document-expiration reminders, milestone email
check-ins). An earlier design assumed n8n; that dependency was dropped in favor of
keeping scheduling version-controlled and testable alongside the application.

## Decision

Run jobs in-process using APScheduler's `AsyncIOScheduler` inside the FastAPI
application. The scheduler is started and stopped by the app's lifespan context
manager. The application is deployed as a single ECS Fargate task with
`desiredCount = 1`; ECS restarts the task automatically on crash.

## Rationale

At MVP scale (hundreds of emails/day, a single-tenant deployment), the complexity
of leader election or PostgreSQL advisory locks does not earn its keep. A single
ECS task with `desiredCount = 1` guarantees exactly one scheduler instance.
`AsyncIOScheduler` runs jobs as coroutines on the existing event loop — correct for
the (thread-unsafe) sync Supabase client. ECS's restart guarantee plus external
monitoring (an UptimeRobot canary pinging `/api/v1/admin/scheduler-health`) provides
sufficient reliability. Jobs are defined in code and registered at startup; no
persistent job store is used.

## Consequences

Horizontal scaling would run duplicate schedulers and double-execute jobs — so it
is out of scope until the architecture changes. Revisit this decision when
sustained CPU exceeds 60%, response p95 exceeds 500ms, or horizontal scaling is
required for any reason.
