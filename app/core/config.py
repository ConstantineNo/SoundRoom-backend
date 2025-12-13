"""
Application configuration constants.
All configuration values should be defined here.
"""

# JWT Configuration (should be moved to environment variables in production)
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Database Configuration
SQLALCHEMY_DATABASE_URL = "sqlite:///./dizi.db"
# SQLALCHEMY_DATABASE_URL = "mysql+pymysql://user:password@localhost/dizi"

# Upload Configuration
UPLOAD_DIR = "uploads"

# Security & Statistics Configuration
WHITELIST_IPS = ["127.0.0.1", "localhost", "::1"]
SENSITIVE_PATHS = [".env", "wp-admin", ".git", ".DS_Store", "phpmyadmin", "config.php"]
RATE_LIMIT_THRESHOLD_PER_SECOND = 50
RATE_LIMIT_THRESHOLD_PER_MINUTE = 60
GEOIP_DB_PATH = "app/core/data/GeoLite2-City.mmdb"
