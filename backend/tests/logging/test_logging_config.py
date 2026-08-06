"""Formatters, the context filter, and job correlation ids.

ContextFilter is the piece that makes the ~200 pre-existing `logger.*` call
sites across the app correlated without touching any of them, so its contract
(stamp request_id on EVERY record, never clobber an explicit one) is worth
pinning.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.core.logging_config import (
    ConsoleFormatter,
    ContextFilter,
    JsonFormatter,
    actor_var,
    get_actor,
    request_id_var,
    set_actor,
)
from app.jobs.scheduler import tracked_job


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


@pytest.fixture(autouse=True)
def _clean_context():
    """Reset both contextvars around each test so ordering cannot matter."""
    request_token = request_id_var.set("")
    actor_token = actor_var.set(None)
    yield
    request_id_var.reset(request_token)
    actor_var.reset(actor_token)


class TestContextFilter:
    def test_stamps_the_current_request_id(self):
        request_id_var.set("abc123")
        record = _record()

        assert ContextFilter().filter(record) is True
        assert record.request_id == "abc123"

    def test_stamps_empty_string_outside_a_request(self):
        record = _record()
        ContextFilter().filter(record)
        assert record.request_id == ""

    def test_does_not_clobber_an_explicitly_supplied_id(self):
        # The request middleware sets request_id via `extra=`; the filter must
        # leave that alone rather than overwrite it from the contextvar.
        request_id_var.set("from-contextvar")
        record = _record(request_id="from-extra")

        ContextFilter().filter(record)
        assert record.request_id == "from-extra"


class TestJsonFormatter:
    def test_emits_one_parseable_object_per_record(self):
        record = _record(request_id="abc123")
        payload = json.loads(JsonFormatter().format(record))

        assert payload["level"] == "INFO"
        assert payload["logger"] == "app.test"
        assert payload["message"] == "hello world"
        assert payload["request_id"] == "abc123"
        assert payload["timestamp"].endswith("+00:00")

    def test_extra_fields_become_top_level_keys(self):
        # This is what makes CloudWatch Logs Insights able to filter on
        # `status` or `duration_ms` without regex-parsing the message.
        record = _record(request_id="abc", status=200, duration_ms=12.5, path="/ping")
        payload = json.loads(JsonFormatter().format(record))

        assert payload["status"] == 200
        assert payload["duration_ms"] == 12.5
        assert payload["path"] == "/ping"

    def test_output_is_a_single_line(self):
        record = _record(request_id="abc")
        assert "\n" not in JsonFormatter().format(record)

    def test_exception_is_serialised_into_the_object(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _record()
            record.exc_info = sys.exc_info()

        payload = json.loads(JsonFormatter().format(record))
        assert "ValueError: boom" in payload["exception"]

    def test_unserialisable_extra_degrades_to_its_string_form(self):
        # A stray UUID or datetime in `extra` must not kill the log call.
        from uuid import uuid4

        value = uuid4()
        record = _record(vendor_id=value)
        payload = json.loads(JsonFormatter().format(record))

        assert payload["vendor_id"] == str(value)


class TestConsoleFormatter:
    def test_shows_a_short_correlation_prefix(self):
        record = _record(request_id="abcdef0123456789")
        assert "[abcdef01]" in ConsoleFormatter().format(record)

    def test_shows_a_dash_outside_a_request(self):
        assert "[-]" in ConsoleFormatter().format(_record())

    def test_appends_extra_fields(self):
        output = ConsoleFormatter().format(_record(request_id="abc", status=200))
        assert "status=200" in output

    def test_scratch_attributes_do_not_leak_into_extras(self):
        # ConsoleFormatter writes short_id/extras onto the record. Formatting the
        # same record twice must not echo them back as caller-supplied fields.
        formatter = ConsoleFormatter()
        record = _record(request_id="abc", status=200)

        formatter.format(record)
        second = formatter.format(record)

        assert "short_id=" not in second
        assert "extras=" not in second


class TestSetActor:
    def test_records_fields(self):
        set_actor(user_id="u-1", role="admin")
        assert get_actor() == {"user_id": "u-1", "role": "admin"}

    def test_merges_rather_than_overwrites(self):
        # get_current_user sets the id, then get_current_active_user adds the
        # role on top. The id must survive.
        set_actor(user_id="u-1")
        set_actor(user_id="u-1", role="admin")
        assert get_actor() == {"user_id": "u-1", "role": "admin"}

    def test_drops_none_values(self):
        set_actor(user_id="u-1", role=None)
        assert get_actor() == {"user_id": "u-1"}

    def test_empty_outside_a_request(self):
        assert get_actor() == {}


class TestJobCorrelationId:
    """Every scheduled job run gets its own id, so a failed nightly job can be
    gathered from the dozens of lines its body emits."""

    @pytest.mark.asyncio
    async def test_job_body_sees_a_correlation_id(self):
        seen = {}

        @tracked_job("test_job")
        async def job():
            seen["request_id"] = request_id_var.get("")
            return {"ok": True}

        await job()
        assert seen["request_id"]
        assert len(seen["request_id"]) == 32

    @pytest.mark.asyncio
    async def test_each_run_gets_a_distinct_id(self):
        seen = []

        @tracked_job("test_job")
        async def job():
            seen.append(request_id_var.get(""))
            return {"ok": True}

        await job()
        await job()
        assert seen[0] != seen[1]

    @pytest.mark.asyncio
    async def test_id_is_reset_after_the_run(self):
        @tracked_job("test_job")
        async def job():
            return {"ok": True}

        await job()
        assert request_id_var.get("") == ""

    @pytest.mark.asyncio
    async def test_id_is_reset_even_when_the_job_fails(self):
        @tracked_job("test_job")
        async def job():
            raise RuntimeError("boom")

        # tracked_job swallows the exception by design so a bad job cannot kill
        # the scheduler; the contextvar must still be cleaned up.
        assert await job() is None
        assert request_id_var.get("") == ""

    @pytest.mark.asyncio
    async def test_job_lines_carry_the_job_id(self, caplog):
        caplog.set_level(logging.INFO, logger="app.jobs.scheduler")

        @tracked_job("test_job")
        async def job():
            return {"ok": True}

        await job()
        records = [r for r in caplog.records if r.name == "app.jobs.scheduler"]
        assert records, "expected start/complete lines from tracked_job"
        assert all(r.job_id == "test_job" for r in records)
        # Start and complete share one id, so the run is greppable end to end.
        assert len({r.request_id for r in records}) == 1
