"""Isolated HTTP tests; never connect to an existing application database."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DIZI_SECRET_KEY"] = "classification-isolated-test-secret"
os.environ["DIZI_DEBUG_ENABLED"] = "false"
# App logging and runtime data stay in the workspace.
os.chdir(ROOT)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.core.deps import get_db
from app.main import app
from app.models.user import User
from app.core.security import create_access_token


@pytest.fixture
def api(tmp_path, monkeypatch):
    from app.services import score_assets
    monkeypatch.setattr(score_assets, "CLASSIFICATION_ASSET_DIR", str(tmp_path / "assets"))
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False, "timeout": 20})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        db.add_all([User(id=1, username="owner", hashed_password="unused", role="user"),
                    User(id=2, username="other", hashed_password="unused", role="user"),
                    User(id=3, username="admin", hashed_password="unused", role="admin")])
        db.commit()

    def sessions():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = sessions
    # Classification tests exercise the real routes/handlers/authentication, without
    # statistics middleware opening an unrelated global database per HTTP request.
    from fastapi import FastAPI
    from app.api.endpoints import scores, classification, private_uploads, playlists, recordings, score_assets
    from app.core.exceptions import AppException
    from app.main import app_exception_handler, http_exception_handler, validation_exception_handler, generic_exception_handler
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError
    isolated = FastAPI()
    isolated.include_router(scores.router, prefix="/scores")
    isolated.include_router(score_assets.router, prefix="/scores")
    isolated.include_router(classification.router)
    isolated.include_router(private_uploads.router)
    isolated.include_router(playlists.router, prefix="/playlists")
    isolated.include_router(recordings.router, prefix="/recordings")
    for exception, handler in ((AppException, app_exception_handler), (HTTPException, http_exception_handler),
                               (RequestValidationError, validation_exception_handler), (Exception, generic_exception_handler)):
        isolated.add_exception_handler(exception, handler)
    isolated.dependency_overrides[get_db] = sessions
    with TestClient(isolated) as client:
        client.factory = factory
        client.headers_for = lambda name="owner": {"Authorization": "Bearer " + create_access_token({"sub": name})}
        yield client
    app.dependency_overrides.clear()
    engine.dispose()
