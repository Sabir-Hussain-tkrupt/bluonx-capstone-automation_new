"""Tests for the health check endpoint."""


def test_health_returns_200(client):
    """GET /health should return 200 with status info."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "bluonx-api"
    assert "version" in data
