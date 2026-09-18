"""
Application configuration constants.
Sensitive values are read from environment variables with dev defaults.
"""

import os

# JWT Configuration
SECRET_KEY = os.getenv("DIZI_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Database Configuration
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dizi.db")

# Upload Configuration
UPLOAD_DIR = "uploads"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_AUDIO_TYPES = {"audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4", "audio/webm"}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

# Security & Statistics Configuration
WHITELIST_IPS = ["127.0.0.1", "localhost", "::1", "testclient"]
SENSITIVE_PATHS = [".env", "wp-admin", ".git", ".DS_Store", "phpmyadmin", "config.php"]
RATE_LIMIT_THRESHOLD_PER_SECOND = 50
RATE_LIMIT_THRESHOLD_PER_MINUTE = 60
GEOIP_DB_PATH = "app/core/data/GeoLite2-City.mmdb"

# Debug Endpoint
DEBUG_ENABLED = os.getenv("DIZI_DEBUG_ENABLED", "false").lower() == "true"

# CHANGE-002: documented retry/candidate windows, in seconds.
CLASSIFICATION_CANDIDATE_TTL = int(os.getenv("CLASSIFICATION_CANDIDATE_TTL", "900"))
CLASSIFICATION_IDEMPOTENCY_TTL = int(os.getenv("CLASSIFICATION_IDEMPOTENCY_TTL", "86400"))

CLASSIFICATION_ASSET_DIR = os.getenv("CLASSIFICATION_ASSET_DIR", "private_score_assets")
CLASSIFICATION_MAX_ASSET_SIZE = int(os.getenv("CLASSIFICATION_MAX_ASSET_SIZE", str(20 * 1024 * 1024)))
