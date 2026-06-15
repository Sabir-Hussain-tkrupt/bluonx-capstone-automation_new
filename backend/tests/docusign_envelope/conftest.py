"""
Shared fixtures for the Task 9.3b DocuSign envelope + Connect webhook tests.

`make_db` returns a MagicMock Supabase client keyed by table + op, with a
`calls` dict recording the first positional arg of every write so a test can
assert exactly what the service wrote (envelope insert, contract/award status
updates). Mirrors backend/tests/awards/conftest.py. Fully offline — no real DB,
no network (DOCUSIGN_PROVIDER=mock / EMAIL_PROVIDER=mock short-circuit sends).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def make_db(spec: dict, calls: dict | None = None) -> MagicMock:
    """Build a Supabase-py-shaped mock.

    `spec[table][op]` supplies the `.data` returned for that op ("select",
    "insert", "update", "delete"), or `spec[table]["default"]`. An Exception
    value is raised from `.execute()`. Storage is stubbed via `.storage`.
    """
    client = MagicMock()

    def _table(name: str):
        tspec = spec.get(name, {})
        chain = MagicMock()
        state = {"op": "select"}

        def _setop(op):
            def _f(*a, **_k):
                state["op"] = op
                if a and calls is not None:
                    calls.setdefault(name, {}).setdefault(op, []).append(a[0])
                return chain

            return _f

        chain.select.side_effect = _setop("select")
        chain.insert.side_effect = _setop("insert")
        chain.update.side_effect = _setop("update")
        chain.delete.side_effect = _setop("delete")
        for m in ("eq", "neq", "in_", "is_", "order", "limit", "single", "maybe_single"):
            getattr(chain, m).return_value = chain

        def _execute(*_a, **_k):
            data = tspec.get(state["op"], tspec.get("default", []))
            if isinstance(data, Exception):
                raise data
            res = MagicMock()
            res.data = data
            return res

        chain.execute.side_effect = _execute
        return chain

    client.table.side_effect = _table
    return client


class FakeEmailService:
    """Records every send_email call; returns a 'sent' result. Stands in for
    EmailService so decline/award sends are counted without SES/network."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_email(self, **kwargs):
        self.sent.append(kwargs)
        res = MagicMock()
        res.status = "sent"
        res.message_id = "fake-msg"
        res.error = None
        return res


class StubDocuSignClient:
    """Stands in for DocuSignClient.send_envelope — records the definition and
    returns a synthetic envelope id (no SDK, no network)."""

    def __init__(self, envelope_id: str = "stub-env-123") -> None:
        self.envelope_id = envelope_id
        self.sent_definitions: list = []

    async def send_envelope(self, envelope_definition) -> str:
        self.sent_definitions.append(envelope_definition)
        return self.envelope_id


@pytest.fixture()
def fake_email() -> FakeEmailService:
    return FakeEmailService()


@pytest.fixture()
def stub_client() -> StubDocuSignClient:
    return StubDocuSignClient()
