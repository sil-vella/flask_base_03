import os

class Config:
    # Debug mode
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1")

    # Toggle SSL for PostgreSQL
    USE_SSL = os.getenv("USE_SSL", "False").lower() in ("true", "1")

    # Database Pool Configuration
    DB_POOL_MIN_CONN = int(os.getenv("DB_POOL_MIN_CONN", "1"))
    DB_POOL_MAX_CONN = int(os.getenv("DB_POOL_MAX_CONN", "10"))
    
    # Flask-Limiter: Redis backend for rate limiting
    RATE_LIMIT_STORAGE_URL = os.getenv("RATE_LIMIT_STORAGE_URL", "redis://localhost:6379/0")

    # Enable or disable logging
    LOGGING_ENABLED = os.getenv("LOGGING_ENABLED", "True").lower() in ("true", "1")
