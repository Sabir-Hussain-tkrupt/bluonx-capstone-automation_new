"""Structured logging: correlation IDs, actor attribution, and formatters.

Deliberately named logging_config, not logging — a module named `logging.py`
inside a package reads as the stdlib module at a glance even though absolute
imports resolve correctly.

The design point is `ContextFilter`: it stamps the current correlation id onto
EVERY LogRecord, so the ~200 existing `logger.*` call sites across the app become
correlated without a single call-site edit. Only two places set the id:

  - `RequestLoggingMiddleware` (app/core/request_logging.py), once per request
  - `tracked_job` (app/jobs/scheduler.py), once per scheduled job run

Actor identity is set by the auth dependencies via `set_actor()` and read back by
the request middleware after the endpoint returns. It is fail-soft: an unset
actor just means those fields are absent from the log line.

Never log request headers, bodies, or query strings from here. Magic-link tokens
travel in POST bodies and `Authorization` carries live JWTs.
"""

from __future__ import annotations

import json
import logging
import logging.config
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any


# ── Context ───────────────────────────────────────────────────────────────

# Correlation id for the current request or job run. Empty string means
# "outside any traced unit of work" (e.g. import-time or startup logging).
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Who is acting, when known: {"user_id": ..., "role": ...} for staff/PM callers,
# {"vendor_id": ..., "actor_kind": "vendor"} for vendor-portal callers.
actor_var: ContextVar[dict[str, Any] | None] = ContextVar("actor", default=None)


def set_actor(**fields: Any) -> None:
    """Record who is behind the current request.

    Called from the auth dependencies once identity is established. Merges into
    any existing actor so a narrower dependency (get_current_user) followed by a
    richer one (get_current_active_user) accumulates rather than overwrites.
    """
    current = actor_var.get() or {}
    actor_var.set({**current, **{k: v for k, v in fields.items() if v is not None}})


def get_actor() -> dict[str, Any]:
    """Actor fields for the current context, or an empty dict when unknown."""
    return dict(actor_var.get() or {})


# ── Log record enrichment ─────────────────────────────────────────────────

# Attributes present on a stock LogRecord. Anything outside this set arrived via
# `logger.info(..., extra={...})` and is worth emitting as its own JSON field.
_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {
    "asctime",
    "message",
    "taskName",
    # Scratch attributes ConsoleFormatter writes onto the record; excluded so a
    # record formatted by more than one handler cannot echo them back as extras.
    "short_id",
    "extras",
    # uvicorn attaches an ANSI-coloured duplicate of its own message on every
    # startup record. It is the same text with escape codes, so emitting it as a
    # field is pure noise.
    "color_message",
}


class ContextFilter(logging.Filter):
    """Attach the current correlation id to every record.

    Attached to the handler (not a logger) so it applies to records from third
    party libraries too, giving one consistent field across the whole stream.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get("")
        return True


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Fields the caller passed via `extra=`, minus the stock LogRecord ones."""
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_ATTRS and key != "request_id"
    }


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for CloudWatch Logs Insights.

    Hand-rolled rather than pulling in python-json-logger: it is a couple of
    dozen lines and avoids a dependency that would have to be pinned, installed,
    and kept in requirements.txt.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
        }
        payload.update(_extra_fields(record))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # default=str so a stray UUID/datetime in `extra` degrades to its string
        # form instead of killing the log call.
        return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable single line for local development.

    Shows a short correlation prefix so interleaved requests stay separable in a
    dev terminal without the noise of full JSON.
    """

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s [%(short_id)s] %(name)s: %(message)s%(extras)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        # Read extras before writing anything onto the record, so the scratch
        # attributes below are never mistaken for caller-supplied fields.
        extras = _extra_fields(record)

        request_id = getattr(record, "request_id", "")
        record.short_id = request_id[:8] if request_id else "-"
        record.extras = (
            " " + " ".join(f"{k}={v}" for k, v in extras.items()) if extras else ""
        )
        return super().format(record)


# ── Configuration ─────────────────────────────────────────────────────────

# Libraries that log per-call at INFO and would otherwise dominate the stream.
# httpx logs every outbound request (Supabase, SES, DocuSign all go through it);
# apscheduler narrates every job registration and execution. Their WARNING and
# ERROR lines (missed job, executor failure) still come through, and our own
# app.jobs.scheduler logging already covers the "started / complete" signal.
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "hpack",
    "apscheduler.executors",
    "apscheduler.scheduler",
)


def configure_logging(level: str | None = None, log_format: str | None = None) -> None:
    """Install the root logging configuration. Call once, before app creation.

    Args default to the values on `settings`; both are overridable so tests can
    configure a formatter without mutating global settings.
    """
    # Imported here rather than at module scope: config.py is imported very
    # early and this module should stay importable without it (tests).
    from app.core.config import settings

    resolved_level = (level or settings.LOG_LEVEL).upper()
    resolved_format = (log_format or settings.LOG_FORMAT or "console").lower()
    formatter = "json" if resolved_format == "json" else "console"

    logging.config.dictConfig(
        {
            "version": 1,
            # Leave loggers created at import time (every `logging.getLogger(__name__)`
            # in the app) attached and working. Disabling them would silence the
            # bulk of our own logging.
            "disable_existing_loggers": False,
            "filters": {
                "context": {"()": ContextFilter},
            },
            "formatters": {
                "json": {"()": JsonFormatter},
                "console": {"()": ConsoleFormatter},
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    # stdout, not stderr: ECS/CloudWatch treats stderr as error
                    # output, and these are ordinary application logs.
                    "stream": "ext://sys.stdout",
                    "formatter": formatter,
                    "filters": ["context"],
                },
            },
            "root": {"handlers": ["default"], "level": resolved_level},
            "loggers": {
                # RequestLoggingMiddleware emits one line per request already.
                # Leaving uvicorn's access log on would double every entry, in a
                # format that carries no correlation id.
                "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": False},
                # Startup/shutdown and error lines should flow through our
                # formatter, so let them propagate to root with no handler of
                # their own.
                "uvicorn": {"handlers": [], "level": resolved_level, "propagate": True},
                "uvicorn.error": {"handlers": [], "level": resolved_level, "propagate": True},
                **{
                    name: {"level": "WARNING", "propagate": True}
                    for name in _NOISY_LOGGERS
                },
            },
        }
    )
