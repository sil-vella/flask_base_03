import os

class Config:
    # Debug mode
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1")

    # Toggle SSL for PostgreSQL
    USE_SSL = os.getenv("USE_SSL", "False").lower() in ("true", "1")

    # Database Pool Configuration
    DB_POOL_MIN_CONN = int(os.getenv("DB_POOL_MIN_CONN", "1"))
    DB_POOL_MAX_CONN = int(os.getenv("DB_POOL_MAX_CONN", "10"))
    
    # Connection Pool Security Settings
    DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))  # Connection timeout in seconds
    DB_STATEMENT_TIMEOUT = int(os.getenv("DB_STATEMENT_TIMEOUT", "30000"))  # Statement timeout in milliseconds
    DB_KEEPALIVES = int(os.getenv("DB_KEEPALIVES", "1"))  # Enable keepalive
    DB_KEEPALIVES_IDLE = int(os.getenv("DB_KEEPALIVES_IDLE", "30"))  # Idle timeout in seconds
    DB_KEEPALIVES_INTERVAL = int(os.getenv("DB_KEEPALIVES_INTERVAL", "10"))  # Keepalive interval in seconds
    DB_KEEPALIVES_COUNT = int(os.getenv("DB_KEEPALIVES_COUNT", "5"))  # Maximum number of keepalive attempts
    DB_MAX_CONNECTIONS_PER_USER = int(os.getenv("DB_MAX_CONNECTIONS_PER_USER", "5"))  # Maximum connections per user
    
    # Resource Protection
    DB_MAX_QUERY_SIZE = int(os.getenv("DB_MAX_QUERY_SIZE", "10000"))  # Maximum query size in bytes
    DB_MAX_RESULT_SIZE = int(os.getenv("DB_MAX_RESULT_SIZE", "1048576"))  # Maximum result size in bytes (1MB)
    
    # Connection Retry Settings
    DB_RETRY_COUNT = int(os.getenv("DB_RETRY_COUNT", "3"))  # Number of connection retry attempts
    DB_RETRY_DELAY = int(os.getenv("DB_RETRY_DELAY", "1"))  # Delay between retries in seconds
    
    # Flask-Limiter: Redis backend for rate limiting
    RATE_LIMIT_STORAGE_URL = os.getenv("RATE_LIMIT_STORAGE_URL", "redis://localhost:6379/0")

    # Enable or disable logging
    LOGGING_ENABLED = os.getenv("LOGGING_ENABLED", "True").lower() in ("true", "1")
