"""Fixtures for the request-logging tests.

Most tests here run against a MINIMAL app rather than app.main, so they exercise
the middleware in isolation without needing the real router tree or a live
Supabase round trip. The one test that proves actor attribution deliberately
mounts the real auth dependency (see test_request_logging.py).
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.request_logging import RequestLoggingMiddleware


@pytest.fixture
def tiny_app() -> FastAPI:
    """A bare app wrapped in the middleware, with one ok route and one that blows up."""
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/items/{item_id}")
    async def item(item_id: str):
        return {"item_id": item_id}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/v1/admin/scheduler-health")
    async def scheduler_health(fail: bool = False):
        if fail:
            return JSONResponse({"status": "down"}, status_code=503)
        return {"status": "healthy"}

    return app


@pytest.fixture
def tiny_client(tiny_app: FastAPI) -> TestClient:
    return TestClient(tiny_app)


@pytest.fixture
def request_records(caplog: pytest.LogCaptureFixture):
    """Capture records from the request logger at DEBUG and return an accessor.

    DEBUG because quiet paths (/health) are logged below INFO on purpose.
    """
    caplog.set_level(logging.DEBUG, logger="app.request")

    def _records() -> list[logging.LogRecord]:
        return [r for r in caplog.records if r.name == "app.request"]

    return _records
