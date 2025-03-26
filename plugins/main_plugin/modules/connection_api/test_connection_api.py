import unittest
import json
import time
import psycopg2
import os
from plugins.main_plugin.modules.connection_api.connection_api import ConnectionAPI
from core.managers.redis_manager import RedisManager

class TestConnectionAPI(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test."""
        self.connection_api = ConnectionAPI()
        self.redis_manager = RedisManager()
        
    def test_redis_encryption(self):
        """Test Redis data encryption and decryption."""
        test_data = {"sensitive": "data", "numbers": [1, 2, 3]}
        
        # Set encrypted data
        self.redis_manager.set("test:encryption", test_data)
        
        # Get and verify decrypted data
        retrieved_data = self.redis_manager.get("test:encryption")
        self.assertEqual(retrieved_data, test_data)
        
        # Verify raw data in Redis is encrypted
        raw_data = self.redis_manager.redis.get("test:encryption")
        self.assertNotEqual(raw_data, json.dumps(test_data))
        
    def test_secure_key_generation(self):
        """Test secure key generation for Redis."""
        prefix = "test"
        args = ["user123", "data456"]
        
        # Generate secure key
        key = self.redis_manager._generate_secure_key(prefix, *args)
        
        # Verify key format
        self.assertTrue(key.startswith(f"{prefix}:"))
        self.assertEqual(len(key.split(":")[1]), 64)  # SHA-256 hash length
        
        # Verify same inputs produce same key
        key2 = self.redis_manager._generate_secure_key(prefix, *args)
        self.assertEqual(key, key2)
        
        # Verify different inputs produce different keys
        key3 = self.redis_manager._generate_secure_key(prefix, "different", "args")
        self.assertNotEqual(key, key3)
        
    def test_redis_password_file(self):
        """Test Redis password loading from file."""
        # Create a temporary password file
        test_password = "test_password_123"
        password_file = "/tmp/test_redis_password"
        with open(password_file, "w") as f:
            f.write(test_password)
            
        # Set environment variable
        os.environ["REDIS_PASSWORD_FILE"] = password_file
        
        # Create new Redis manager instance
        redis_manager = RedisManager()
        
        # Test connection
        self.assertTrue(redis_manager.redis.ping())
        
        # Clean up
        os.remove(password_file)
        del os.environ["REDIS_PASSWORD_FILE"]
        
    def test_connection_state_tracking(self):
        """Test Redis connection state tracking with security features."""
        # Get a connection and verify Redis state
        conn = self.connection_api.get_connection()
        conn_id = id(conn)
        
        # Verify connection state in Redis (now encrypted)
        conn_state = self.connection_api.redis_manager.get(f"connection:{conn_id}")
        self.assertIsNotNone(conn_state)
        self.assertEqual(conn_state['status'], 'active')
        self.assertIn('created_at', conn_state)
        self.assertIn('statement_timeout', conn_state)
        self.assertIn('last_used', conn_state)
        
        # Return connection and verify updated state
        self.connection_api.return_connection(conn)
        updated_state = self.connection_api.redis_manager.get(f"connection:{conn_id}")
        self.assertEqual(updated_state['status'], 'returned')
        self.assertIn('returned_at', updated_state)

    def test_connection_security_features(self):
        """Test connection security features."""
        conn = self.connection_api.get_connection()
        try:
            # Test statement timeout
            with conn.cursor() as cur:
                cur.execute("SELECT pg_sleep(2)")  # Should succeed
                cur.execute("SELECT pg_sleep(31)")  # Should fail due to timeout
                self.fail("Statement timeout not enforced")
        except psycopg2.OperationalError as e:
            self.assertIn("statement timeout", str(e).lower())
        finally:
            self.connection_api.return_connection(conn)

    def test_connection_retry_logic(self):
        """Test connection retry logic."""
        # Temporarily modify pool to force connection failure
        original_pool = self.connection_api.connection_pool
        self.connection_api.connection_pool = None
        
        try:
            # This should trigger retry logic
            conn = self.connection_api.get_connection()
            self.assertIsNotNone(conn)
            self.connection_api.return_connection(conn)
        finally:
            self.connection_api.connection_pool = original_pool

    def test_query_caching(self):
        """Test Redis query result caching with security features."""
        query = "SELECT 1 as test"
        
        # First call should hit the database
        result = self.connection_api.fetch_from_db(query)
        self.assertEqual(result, [(1,)])
        
        # Second call should hit the cache (now encrypted)
        cached_result = self.connection_api.fetch_from_db(query)
        self.assertEqual(cached_result, [(1,)])

    def test_cache_invalidation(self):
        """Test Redis cache invalidation on write operations."""
        # Create a test table
        create_table = """
        CREATE TABLE IF NOT EXISTS test_cache (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50)
        );
        """
        self.connection_api.execute_query(create_table)
        
        # Clear any existing data
        self.connection_api.execute_query("DELETE FROM test_cache")
        
        # Insert data and verify cache invalidation
        insert_query = "INSERT INTO test_cache (name) VALUES (%s)"
        self.connection_api.execute_query(insert_query, ("test",))
        
        # Verify the data was inserted
        select_query = "SELECT name FROM test_cache WHERE name = 'test'"
        result = self.connection_api.fetch_from_db(select_query)
        self.assertEqual(result, [('test',)])
        
        # Clean up
        self.connection_api.execute_query("DROP TABLE test_cache")

    def test_user_data_caching(self):
        """Test Redis caching for user data."""
        user_data = {
            "id": 1,
            "username": "test_user",
            "email": "test@example.com"
        }
        
        # Cache user data (now encrypted)
        self.connection_api.cache_user_data(1, user_data)
        
        # Retrieve cached data
        cached_data = self.connection_api.get_cached_user_data(1)
        self.assertEqual(cached_data, user_data)

    def test_guessed_names_caching(self):
        """Test Redis caching for guessed names."""
        # Create test table
        create_table = """
        CREATE TABLE IF NOT EXISTS guessed_names (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            name VARCHAR(50)
        );
        """
        self.connection_api.execute_query(create_table)
        
        # Test data
        guessed_names = ["name1", "name2", "name3"]
        
        # Cache guessed names (now encrypted)
        self.connection_api.cache_guessed_names(1, guessed_names)
        
        # Retrieve cached names
        cached_names = self.connection_api.get_cached_guessed_names(1)
        self.assertEqual(cached_names, guessed_names)
        
        # Clean up
        self.connection_api.execute_query("DROP TABLE guessed_names")

    def test_cache_invalidation_on_add_guessed_name(self):
        """Test Redis cache invalidation when adding guessed names."""
        # Create test table if not exists
        create_table = """
        CREATE TABLE IF NOT EXISTS guessed_names (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            name VARCHAR(50)
        );
        """
        self.connection_api.execute_query(create_table)
        
        # Initial guessed names
        initial_names = ["name1", "name2"]
        self.connection_api.cache_guessed_names(1, initial_names)
        
        # Add new guessed name
        self.connection_api.add_guessed_name(1, "name3")
        
        # Verify cache was invalidated
        cached_names = self.connection_api.get_cached_guessed_names(1)
        self.assertIsNone(cached_names)  # Cache should be invalidated
        
        # Clean up
        self.connection_api.execute_query("DROP TABLE guessed_names")

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self.connection_api, 'connection_pool') and self.connection_api.connection_pool:
            self.connection_api.connection_pool.closeall()
        if hasattr(self.connection_api, 'redis_manager'):
            self.connection_api.redis_manager.dispose()

if __name__ == '__main__':
    unittest.main() 