"""Phase 1 tests: P0 security fixes verification."""

import os
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core import config


def _reload_config():
    """Reload config module to pick up env changes."""
    import importlib
    importlib.reload(config)


@pytest.fixture
def client():
    return TestClient(app)


def _register_and_login(client: TestClient, username: str = "testuser1"):
    """Helper: register and return auth header."""
    client.post("/auth/register", json={"username": username, "password": "testpass123"})
    resp = client.post("/auth/login", data={"username": username, "password": "testpass123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── 1. Auth on write endpoints ──

def test_create_score_requires_auth(client):
    """Unauthenticated POST /scores/ must return 401."""
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg"),
        "audio": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg"),
    }
    resp = client.post("/scores/", data={"title": "t", "song_key": "C", "flute_key": "C", "fingering": "C"}, files=files)
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


def test_update_abc_requires_auth(client):
    """Unauthenticated PUT /scores/{id}/abc must return 401."""
    resp = client.put("/scores/1/abc", json={"abc_content": "X:1\nT:Test\nK:C\n| C D |"})
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


def test_authenticated_create_score_works(client):
    """Authenticated user can create a score."""
    headers = _register_and_login(client)
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake\x00\x01\x02"), "image/jpeg"),
        "audio": ("test.mp3", io.BytesIO(b"fake\x00\x01\x02"), "audio/mpeg"),
    }
    resp = client.post(
        "/scores/",
        data={"title": "Auth Test", "song_key": "C", "flute_key": "C", "fingering": "C"},
        files=files,
        headers=headers,
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json()["title"] == "Auth Test"


def test_authenticated_update_abc_works(client):
    """Authenticated user can update ABC on a score."""
    headers = _register_and_login(client)
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg"),
        "audio": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg"),
    }
    create_resp = client.post(
        "/scores/",
        data={"title": "ABC Test", "song_key": "G", "flute_key": "C", "fingering": "3"},
        files=files,
        headers=headers,
    )
    score_id = create_resp.json()["id"]

    resp = client.put(
        f"/scores/{score_id}/abc",
        json={"abc_content": "X:1\nT:Updated\nK:D\nM:4/4\nL:1/4\n| D E F G |"},
        headers=headers,
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json()["abc_source"] is not None


# ── 2. File upload validation ──

def test_invalid_image_type_rejected(client):
    """Upload with non-image type is rejected."""
    headers = _register_and_login(client)
    files = {
        "image": ("test.txt", io.BytesIO(b"not an image"), "text/plain"),
        "audio": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg"),
    }
    resp = client.post("/scores/", data={"title": "t", "song_key": "C", "flute_key": "C", "fingering": "C"}, files=files, headers=headers)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


def test_invalid_audio_type_rejected(client):
    """Upload with non-audio type is rejected."""
    headers = _register_and_login(client)
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg"),
        "audio": ("test.exe", io.BytesIO(b"evil"), "application/x-msdownload"),
    }
    resp = client.post("/scores/", data={"title": "t", "song_key": "C", "flute_key": "C", "fingering": "C"}, files=files, headers=headers)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


def test_invalid_recording_type_rejected(client):
    """Upload recording with non-audio type is rejected."""
    headers = _register_and_login(client)
    resp = client.post(
        "/recordings/",
        data={"score_id": "1"},
        files={"file": ("malware.exe", io.BytesIO(b"evil"), "application/x-msdownload")},
        headers=headers,
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


# ── 3. SECRET_KEY environment variable ──

def test_missing_secret_key_uses_dev_default(monkeypatch):
    """When DIZI_SECRET_KEY is not set, dev default is used (app starts)."""
    monkeypatch.delenv("DIZI_SECRET_KEY", raising=False)
    # Re-import triggers re-read of env
    _reload_config()
    from app.core.config import SECRET_KEY
    assert SECRET_KEY == "dev-secret-change-in-production"


def test_custom_secret_key_from_env(monkeypatch):
    """DIZI_SECRET_KEY env var is respected."""
    monkeypatch.setenv("DIZI_SECRET_KEY", "my-production-secret")
    _reload_config()
    from app.core.config import SECRET_KEY
    assert SECRET_KEY == "my-production-secret"


# ── 4. Debug endpoint gating ──

def test_debug_disabled_by_default(client):
    """Debug endpoints return 404 when not enabled."""
    resp1 = client.post("/debug/log", json={
        "timestamp": 1.0,
        "userAgent": "test",
        "audioContext": {"sampleRate": 44100, "state": "running", "baseLatency": 0.01, "outputLatency": 0.02},
    })
    resp2 = client.get("/debug/logs")
    assert resp1.status_code == 404
    assert resp2.status_code == 404
