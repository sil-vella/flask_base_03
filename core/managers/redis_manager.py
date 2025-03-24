import os
import redis
from redis import Redis
from redis.connection import ConnectionPool
from typing import Optional, Any, Union, List
from tools.logger.custom_logging import custom_log

class RedisManager:
    _instance = None
    _pool = None
    _redis_client = None
    _test_mode = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._pool:
            self._initialize_pool()

    def _initialize_pool(self):
        """Initialize Redis connection pool."""
        try:
            # Read password from secret file
            with open(os.getenv("REDIS_PASSWORD_FILE"), 'r') as f:
                redis_password = f.read().strip()

            # Create connection pool
            self._pool = ConnectionPool(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                db=int(os.getenv("REDIS_DB", 0)),
                password=redis_password,
                decode_responses=True,  # Automatically decode responses to strings
                max_connections=10  # Maximum number of connections in the pool
            )
            custom_log("✅ Redis connection pool initialized")
        except Exception as e:
            custom_log(f"❌ Error initializing Redis pool: {e}")
            raise

    @property
    def client(self) -> Redis:
        """Get Redis client instance."""
        if not self._redis_client:
            try:
                self._redis_client = redis.Redis(connection_pool=self._pool)
                # Test connection
                self._redis_client.ping()
                custom_log("✅ Redis client initialized and connected")
            except Exception as e:
                custom_log(f"❌ Error creating Redis client: {e}")
                raise
        return self._redis_client

    def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        try:
            value = self.client.get(key)
            custom_log(f"✅ Retrieved key: {key}")
            return value
        except Exception as e:
            custom_log(f"❌ Error getting key {key}: {e}")
            return None

    def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """Set key-value pair with optional expiration."""
        try:
            self.client.set(key, value, ex=expire)
            custom_log(f"✅ Set key: {key}")
            return True
        except Exception as e:
            custom_log(f"❌ Error setting key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete a key."""
        try:
            self.client.delete(key)
            custom_log(f"✅ Deleted key: {key}")
            return True
        except Exception as e:
            custom_log(f"❌ Error deleting key {key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            custom_log(f"❌ Error checking existence of key {key}: {e}")
            return False

    def expire(self, key: str, seconds: int) -> bool:
        """Set expiration time for a key."""
        try:
            return bool(self.client.expire(key, seconds))
        except Exception as e:
            custom_log(f"❌ Error setting expiration for key {key}: {e}")
            return False

    def ttl(self, key: str) -> int:
        """Get remaining time to live of a key."""
        try:
            return self.client.ttl(key)
        except Exception as e:
            custom_log(f"❌ Error getting TTL for key {key}: {e}")
            return -2  # Key does not exist

    def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment value of a key."""
        try:
            return self.client.incr(key, amount)
        except Exception as e:
            custom_log(f"❌ Error incrementing key {key}: {e}")
            return None

    def decr(self, key: str, amount: int = 1) -> Optional[int]:
        """Decrement value of a key."""
        try:
            return self.client.decr(key, amount)
        except Exception as e:
            custom_log(f"❌ Error decrementing key {key}: {e}")
            return None

    def hset(self, name: str, key: str, value: str) -> bool:
        """Set hash field."""
        try:
            return bool(self.client.hset(name, key, value))
        except Exception as e:
            custom_log(f"❌ Error setting hash field {key} in {name}: {e}")
            return False

    def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field."""
        try:
            return self.client.hget(name, key)
        except Exception as e:
            custom_log(f"❌ Error getting hash field {key} from {name}: {e}")
            return None

    def hdel(self, name: str, key: str) -> bool:
        """Delete hash field."""
        try:
            return bool(self.client.hdel(name, key))
        except Exception as e:
            custom_log(f"❌ Error deleting hash field {key} from {name}: {e}")
            return False

    def hgetall(self, name: str) -> dict:
        """Get all hash fields and values."""
        try:
            return self.client.hgetall(name)
        except Exception as e:
            custom_log(f"❌ Error getting all hash fields from {name}: {e}")
            return {}

    def lpush(self, name: str, value: str) -> Optional[int]:
        """Push value to list."""
        try:
            return self.client.lpush(name, value)
        except Exception as e:
            custom_log(f"❌ Error pushing to list {name}: {e}")
            return None

    def rpush(self, name: str, value: str) -> Optional[int]:
        """Push value to end of list."""
        try:
            return self.client.rpush(name, value)
        except Exception as e:
            custom_log(f"❌ Error pushing to end of list {name}: {e}")
            return None

    def lpop(self, name: str) -> Optional[str]:
        """Pop value from list."""
        try:
            return self.client.lpop(name)
        except Exception as e:
            custom_log(f"❌ Error popping from list {name}: {e}")
            return None

    def rpop(self, name: str) -> Optional[str]:
        """Pop value from end of list."""
        try:
            return self.client.rpop(name)
        except Exception as e:
            custom_log(f"❌ Error popping from end of list {name}: {e}")
            return None

    def lrange(self, name: str, start: int, end: int) -> List[str]:
        """Get range of values from list."""
        try:
            return self.client.lrange(name, start, end)
        except Exception as e:
            custom_log(f"❌ Error getting range from list {name}: {e}")
            return []

    def dispose(self):
        """Clean up Redis connections."""
        try:
            if self._redis_client:
                self._redis_client.close()
            if self._pool:
                self._pool.disconnect()
            custom_log("✅ Redis connections closed")
        except Exception as e:
            custom_log(f"❌ Error disposing Redis connections: {e}") 