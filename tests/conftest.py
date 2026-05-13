"""Pytest fixtures for the test suite."""

import pytest
from app.core.database import SessionLocal
from app.models.statistics import BannedIP
from app.services.security_service import SecurityService


@pytest.fixture(autouse=True)
def _clear_security_state():
    """Clear rate limit caches and bans before each test to avoid cross-test contamination."""
    SecurityService._request_timestamps.clear()
    SecurityService._sensitive_path_hits.clear()
    SecurityService._banned_ips_cache.clear()
    SecurityService._last_cache_update = 0

    db = SessionLocal()
    try:
        db.query(BannedIP).filter(BannedIP.is_active == True).update({BannedIP.is_active: False})
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
