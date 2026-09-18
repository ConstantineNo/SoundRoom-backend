"""Boot the real application/middleware against a migrated isolated database."""
import os
from pathlib import Path
import subprocess
import sys


def test_full_app_migrations_auth_cors_and_routes(tmp_path):
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{tmp_path / "app.db"}',
           'TMPDIR': str(tmp_path), 'MPLCONFIGDIR': str(tmp_path / 'mpl'), 'XDG_CACHE_HOME': str(tmp_path / 'cache')}
    script = '''
from alembic.config import Config
from alembic import command
command.upgrade(Config("alembic.ini"), "head")
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import create_access_token
with SessionLocal() as db:
    db.add(User(username="boot", hashed_password="unused", role="user"))
    db.commit()
with TestClient(app) as client:
    token = create_access_token({"sub":"boot"})
    headers = {"Authorization":"Bearer " + token, "Idempotency-Key":"boot", "Origin":"http://localhost:5173"}
    result = client.post("/scores/", json={"title":"联调", "original_key":"D", "fingering":{"code":"closed_2"}}, headers=headers)
    assert result.status_code == 201, result.text
    assert "etag" in result.headers.get("access-control-expose-headers", "").lower()
    assert result.headers["access-control-allow-origin"] == "*"
    sid = result.json()["data"]["id"]
    fetched = client.get(f"/scores/{sid}", headers=headers)
    assert fetched.status_code == 200 and fetched.headers["etag"] == result.headers["etag"]
    assert client.get(f"/scores/{sid}").status_code == 404
    assert client.get("/scores/?scope=mine", headers=headers).json()["data"]["total"] == 1
    options = client.options(f"/scores/{sid}", headers={"Origin":"http://localhost:5173", "Access-Control-Request-Method":"PATCH", "Access-Control-Request-Headers":"if-match,authorization"})
    assert options.status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    expected = {"/score-classification-options", "/flute-key-candidates", "/score-categories", "/scores/", "/scores/{score_id}",
        "/scores/{score_id}/arrangements", "/scores/{score_id}/arrangements/{arrangement_id}", "/scores/{score_id}/assets",
        "/scores/{score_id}/assets/{asset_id}", "/scores/{score_id}/arrangements/{arrangement_id}/notation-bindings",
        "/scores/{score_id}/arrangements/{arrangement_id}/practice-capability", "/scores/{score_id}/publish",
        "/scores/{score_id}/unpublish", "/scores/{score_id}/copies"}
    assert expected <= paths.keys(), expected - paths.keys()
print("full application smoke passed")
'''
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'full application smoke passed' in result.stdout
