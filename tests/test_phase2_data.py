"""Phase 2 tests: audit fields, owner, unique constraint, FK enforcement."""

import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import SessionLocal


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def _register_and_login(client: TestClient, username: str = "p2user"):
    client.post("/auth/register", json={"username": username, "password": "testpass123"})
    resp = client.post("/auth/login", data={"username": username, "password": "testpass123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── 1. Audit fields: created_at / updated_at ──

def test_score_has_created_at(client, db: Session):
    """Newly created score has created_at set."""
    headers = _register_and_login(client)
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg"),
        "audio": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg"),
    }
    resp = client.post(
        "/scores/",
        data={"title": "Audit Test", "song_key": "C", "flute_key": "C", "fingering": "C"},
        files=files,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_at"] is not None, f"created_at missing: {data}"
    assert data["updated_at"] is not None, f"updated_at missing: {data}"


def test_user_has_created_at(client, db: Session):
    """Newly registered user has created_at set."""
    import random, string
    uname = "audituser_" + "".join(random.choices(string.ascii_lowercase, k=6))
    resp = client.post("/auth/register", json={"username": uname, "password": "testpass123"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["created_at"] is not None, f"created_at missing: {data}"


def test_updated_at_changes_on_update(client, db: Session):
    """After updating ABC, updated_at should change."""
    import random, string, time
    uname = "updater_" + "".join(random.choices(string.ascii_lowercase, k=6))
    headers = _register_and_login(client, uname)
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg"),
        "audio": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg"),
    }
    create_resp = client.post(
        "/scores/",
        data={"title": "Update Test", "song_key": "C", "flute_key": "C", "fingering": "C"},
        files=files,
        headers=headers,
    )
    assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
    score_id = create_resp.json()["id"]
    original_updated_at = create_resp.json()["updated_at"]

    time.sleep(1.0)

    put_resp = client.put(
        f"/scores/{score_id}/abc",
        json={"abc_content": "X:1\nT:Changed\nK:G\nM:4/4\nL:1/4\n| G A B c |"},
        headers=headers,
    )
    assert put_resp.status_code == 200, f"PUT failed: {put_resp.text}"

    get_resp = client.get(f"/scores/{score_id}")
    new_updated_at = get_resp.json()["updated_at"]
    assert new_updated_at != original_updated_at, \
        f"updated_at did not change: {original_updated_at} → {new_updated_at}"


# ── 2. Score owner (created_by) ──

def test_score_has_created_by(client):
    """Created score records the creator's user ID."""
    headers = _register_and_login(client, "owner1")
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg"),
        "audio": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg"),
    }
    resp = client.post(
        "/scores/",
        data={"title": "Owner Test", "song_key": "C", "flute_key": "C", "fingering": "C"},
        files=files,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_by"] is not None, f"created_by missing: {data}"


# ── 3. Playlist items unique constraint ──

def test_duplicate_playlist_item_rejected(client):
    """Adding the same score twice to a playlist is rejected."""
    headers = _register_and_login(client, "playlist1")
    # Create score
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg"),
        "audio": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg"),
    }
    score_resp = client.post(
        "/scores/",
        data={"title": "Dup Test", "song_key": "C", "flute_key": "C", "fingering": "C"},
        files=files,
        headers=headers,
    )
    score_id = score_resp.json()["id"]

    # Create playlist
    playlist_resp = client.post("/playlists/", json={"name": "Test"}, headers=headers)
    playlist_id = playlist_resp.json()["id"]

    # Add item first time — should succeed
    item1 = client.post(f"/playlists/{playlist_id}/items?score_id={score_id}", headers=headers)
    assert item1.status_code == 200, f"First add failed: {item1.text}"

    # Add same item second time — should fail (unique constraint)
    item2 = client.post(f"/playlists/{playlist_id}/items?score_id={score_id}", headers=headers)
    assert item2.status_code == 400, f"Expected 400 for duplicate, got {item2.status_code}: {item2.text}"


# ── 4. Foreign key enforcement ──

def test_recording_with_invalid_score_rejected(client):
    """Creating recording with non-existent score_id is rejected."""
    headers = _register_and_login(client, "fktest1")
    resp = client.post(
        "/recordings/",
        data={"score_id": "99999"},
        files={"file": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg")},
        headers=headers,
    )
    assert resp.status_code in (404, 400), f"Expected 4xx, got {resp.status_code}"


def test_playlist_with_invalid_score_rejected(client):
    """Adding non-existent score to playlist is rejected."""
    headers = _register_and_login(client, "fktest2")
    playlist_resp = client.post("/playlists/", json={"name": "FK Test"}, headers=headers)
    playlist_id = playlist_resp.json()["id"]
    resp = client.post(f"/playlists/{playlist_id}/items?score_id=99999", headers=headers)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
