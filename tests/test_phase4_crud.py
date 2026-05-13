"""Phase 4 tests: complete CRUD operations and owner isolation."""

import io
import random
import string
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _register_and_login(client: TestClient, username: str = None):
    if username is None:
        username = "p4_" + "".join(random.choices(string.ascii_lowercase, k=6))
    client.post("/auth/register", json={"username": username, "password": "testpass123"})
    resp = client.post("/auth/login", data={"username": username, "password": "testpass123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_score(client, headers):
    files = {
        "image": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg"),
        "audio": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg"),
    }
    resp = client.post(
        "/scores/",
        data={"title": "P4 Score", "song_key": "C", "flute_key": "C", "fingering": "C"},
        files=files,
        headers=headers,
    )
    return resp.json()["id"]


# ── Playlists CRUD ──

def test_rename_playlist(client):
    h = _register_and_login(client)
    resp = client.post("/playlists/", json={"name": "Old"}, headers=h)
    pid = resp.json()["id"]
    resp = client.put(f"/playlists/{pid}?name=NewName", headers=h)
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewName"


def test_delete_playlist(client):
    h = _register_and_login(client)
    resp = client.post("/playlists/", json={"name": "DelMe"}, headers=h)
    pid = resp.json()["id"]
    resp = client.delete(f"/playlists/{pid}", headers=h)
    assert resp.status_code == 200


def test_remove_item_from_playlist(client):
    h = _register_and_login(client)
    sid = _create_score(client, h)
    resp = client.post("/playlists/", json={"name": "Items"}, headers=h)
    pid = resp.json()["id"]
    item = client.post(f"/playlists/{pid}/items?score_id={sid}", headers=h)
    item_id = item.json()["id"]
    resp = client.delete(f"/playlists/{pid}/items/{item_id}", headers=h)
    assert resp.status_code == 200


def test_reorder_playlist_item(client):
    h = _register_and_login(client)
    sid = _create_score(client, h)
    resp = client.post("/playlists/", json={"name": "Reorder"}, headers=h)
    pid = resp.json()["id"]
    item = client.post(f"/playlists/{pid}/items?score_id={sid}", headers=h)
    item_id = item.json()["id"]
    resp = client.put(f"/playlists/{pid}/items/{item_id}/sort?sort_order=99", headers=h)
    assert resp.status_code == 200
    assert resp.json()["sort_order"] == 99


# ── Recordings delete ──

def test_delete_recording(client):
    h = _register_and_login(client)
    sid = _create_score(client, h)
    resp = client.post(
        "/recordings/",
        data={"score_id": str(sid)},
        files={"file": ("test.mp3", io.BytesIO(b"fake"), "audio/mpeg")},
        headers=h,
    )
    rid = resp.json()["id"]
    resp = client.delete(f"/recordings/{rid}", headers=h)
    assert resp.status_code == 200


# ── Scores update metadata and delete ──

def test_update_score_metadata(client):
    h = _register_and_login(client)
    sid = _create_score(client, h)
    resp = client.put(f"/scores/{sid}", json={"title": "Updated Title"}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"


def test_delete_score(client):
    h = _register_and_login(client)
    sid = _create_score(client, h)
    resp = client.delete(f"/scores/{sid}", headers=h)
    assert resp.status_code == 200


# ── Change password ──

def test_change_password(client):
    uname = "pwduser_" + "".join(random.choices(string.ascii_lowercase, k=6))
    h = _register_and_login(client, uname)
    resp = client.put("/auth/me/password", json={
        "current_password": "testpass123",
        "new_password": "newpass456",
    }, headers=h)
    assert resp.status_code == 200

    # Verify new password works
    login_resp = client.post("/auth/login", data={"username": uname, "password": "newpass456"})
    assert login_resp.status_code == 200


def test_change_password_wrong_current(client):
    uname = "pwduser2_" + "".join(random.choices(string.ascii_lowercase, k=6))
    h = _register_and_login(client, uname)
    resp = client.put("/auth/me/password", json={
        "current_password": "wrongpass",
        "new_password": "newpass789",
    }, headers=h)
    assert resp.status_code == 400


# ── Owner isolation ──

def test_playlist_not_visible_to_other_user(client):
    h1 = _register_and_login(client, "ownerA")
    h2 = _register_and_login(client, "ownerB")

    client.post("/playlists/", json={"name": "Secret"}, headers=h1)
    resp = client.get("/playlists/", headers=h2)
    assert resp.status_code == 200
    assert len(resp.json()) == 0  # User B doesn't see User A's playlist


def test_recording_not_visible_to_other_user(client):
    h1 = _register_and_login(client, "recA")
    h2 = _register_and_login(client, "recB")
    sid = _create_score(client, h1)
    client.post("/recordings/", data={"score_id": str(sid)},
                 files={"file": ("t.mp3", io.BytesIO(b"x"), "audio/mpeg")}, headers=h1)
    resp = client.get("/recordings/", headers=h2)
    assert resp.status_code == 200
    assert len(resp.json()) == 0
