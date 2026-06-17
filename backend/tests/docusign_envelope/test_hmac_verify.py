"""HMAC verification of the raw Connect body + the 401 gate (Task 9.3b Part B)."""

import base64
import hashlib
import hmac
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.routers.docusign_webhooks import extract_event, verify_connect_hmac

from .conftest import make_db

_KEY = "super-secret-connect-hmac-key"


def _sign(raw: bytes, key: str = _KEY) -> str:
    return base64.b64encode(
        hmac.new(key.encode(), raw, hashlib.sha256).digest()
    ).decode("ascii")


@pytest.fixture(autouse=True)
def _set_key(monkeypatch):
    monkeypatch.setattr(settings, "DOCUSIGN_CONNECT_HMAC_KEY", _KEY)


# ── Pure verifier ──────────────────────────────────────────────────────────


def test_valid_signature_passes():
    raw = b'{"event":"envelope-completed"}'
    assert verify_connect_hmac(raw, _sign(raw)) is True


def test_tampered_body_fails():
    raw = b'{"event":"envelope-completed"}'
    sig = _sign(raw)
    assert verify_connect_hmac(b'{"event":"envelope-voided"}', sig) is False


def test_bad_signature_fails():
    raw = b'{"event":"envelope-completed"}'
    assert verify_connect_hmac(raw, "not-a-real-signature") is False


def test_missing_signature_fails():
    assert verify_connect_hmac(b"{}", None) is False


def test_missing_key_fails(monkeypatch):
    monkeypatch.setattr(settings, "DOCUSIGN_CONNECT_HMAC_KEY", None)
    raw = b"{}"
    assert verify_connect_hmac(raw, _sign(raw)) is False


# ── Event extraction ───────────────────────────────────────────────────────


def test_extract_event_completed_json_sim():
    payload = {
        "event": "envelope-completed",
        "data": {
            "envelopeId": "abc-123",
            "envelopeSummary": {"status": "completed"},
        },
    }
    env_id, status = extract_event(payload)
    assert env_id == "abc-123"
    assert status == "completed"


# ── HTTP gate ──────────────────────────────────────────────────────────────


def test_endpoint_rejects_bad_signature_401():
    raw = b'{"event":"envelope-completed","data":{"envelopeId":"x"}}'
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/webhooks/docusign-connect",
            content=raw,
            headers={"X-DocuSign-Signature-1": "wrong"},
        )
    assert resp.status_code == 401


def test_endpoint_accepts_valid_signature_unknown_envelope_200():
    raw = b'{"event":"envelope-completed","data":{"envelopeId":"unknown-env","envelopeSummary":{"status":"completed"}}}'
    mock_db = make_db({"docusign_envelopes": {"select": []}})
    # The route calls get_supabase(request) directly (not via Depends), so patch it.
    with patch("app.routers.docusign_webhooks.get_supabase", return_value=mock_db):
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/webhooks/docusign-connect",
                content=raw,
                headers={"X-DocuSign-Signature-1": _sign(raw)},
            )
    assert resp.status_code == 200
