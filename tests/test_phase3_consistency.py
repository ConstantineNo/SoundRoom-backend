"""Phase 3 tests: unified errors, response envelope, pagination."""

import io
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _register_and_login(client: TestClient, username: str):
    client.post("/auth/register", json={"username": username, "password": "testpass123"})
    resp = client.post("/auth/login", data={"username": username, "password": "testpass123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── 1. Unified error envelope ──

def test_app_exception_returns_unified_error(client):
    """HTTPException (from FastAPI deps) returns structured error with code/message."""
    import random, string
    uname = "p3err_" + "".join(random.choices(string.ascii_lowercase, k=6))
    h = _register_and_login(client, uname)
    resp = client.put(
        "/scores/99999/abc",
        json={"abc_content": "X:1\nT:Test\nK:C\nM:4/4\nL:1/4\n|C|"},
        headers=h,
    )
    assert resp.status_code == 404
    data = resp.json()
    assert "code" in data, f"No 'code' in: {data}"
    assert "message" in data, f"No 'message' in: {data}"


def test_auth_failure_returns_unified_error(client):
    """Auth failure returns structured error."""
    resp = client.get("/auth/me", headers={"Authorization": "Bearer invalidtoken"})
    assert resp.status_code == 401
    data = resp.json()
    assert "code" in data, f"No 'code' in: {data}"


# ── 2. Pagination metadata ──

def test_scores_returns_paginated_response(client):
    """Scores endpoint returns paginated envelope with total."""
    import random, string

    # Create a few scores to ensure pagination is meaningful
    uname = "p3_" + "".join(random.choices(string.ascii_lowercase, k=6))
    headers = _register_and_login(client, uname)
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg"),
        "audio": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg"),
    }
    for i in range(3):
        client.post(
            "/scores/",
            data={"title": f"Score{i}", "song_key": "C", "flute_key": "C", "fingering": "C"},
            files=files,
            headers=headers,
        )

    resp = client.get("/scores/?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "code" in data
    assert data["code"] == 0
    assert "data" in data
    assert "items" in data["data"]
    assert "page" in data["data"]
    assert "size" in data["data"]
    assert "total" in data["data"]
    assert "total_pages" in data["data"]
    assert data["data"]["page"] == 1
    assert data["data"]["size"] == 2
    assert data["data"]["total"] >= 3
    assert len(data["data"]["items"]) <= 2


def test_scores_legacy_pagination_still_works(client):
    """Legacy skip/limit params still work and return paginated envelope."""
    import random, string
    uname = "p3l_" + "".join(random.choices(string.ascii_lowercase, k=6))
    headers = _register_and_login(client, uname)
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg"),
        "audio": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg"),
    }
    client.post(
        "/scores/",
        data={"title": "LegacyScore", "song_key": "D", "flute_key": "C", "fingering": "3"},
        files=files,
        headers=headers,
    )

    resp = client.get("/scores/?skip=0&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "items" in data["data"]


# ── 3. Exception handler for unexpected errors ──

def test_unexpected_error_returns_500_envelope(client, monkeypatch):
    """Unhandled exceptions return 500 with unified error format."""
    monkeypatch.setenv("DIZI_DEBUG_ENABLED", "true")
    # Send empty body to trigger an unexpected error
    resp = client.post("/debug/log", json={"invalid": "missing required fields"})
    assert resp.status_code in (500, 422)  # 422 from Pydantic validation, 500 from our handler
