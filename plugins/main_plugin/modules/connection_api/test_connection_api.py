import unittest
import json
import time
import psycopg2
from plugins.main_plugin.modules.connection_api.connection_api import ConnectionAPI

class TestConnectionAPI(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test."""
        self.connection_api = ConnectionAPI()
        
    def test_connection_state_tracking(self):
        """Test Redis connection state tracking with security features."""
        # Get a connection and verify Redis state
        conn = self.connection_api.get_connection()
        conn_id = id(conn)
        
        # Verify connection state in Redis
        conn_state = json.loads(self.connection_api.redis_manager.get(f"connection:{conn_id}"))
        self.assertIsNotNone(conn_state)
        self.assertEqual(conn_state['status'], 'active')
        self.assertIn('created_at', conn_state)
        self.assertIn('statement_timeout', conn_state)
        self.assertIn('last_used', conn_state)
        
        # Return connection and verify updated state
        self.connection_api.return_connection(conn)
        updated_state = json.loads(self.connection_api.redis_manager.get(f"connection:{conn_id}"))
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
        
        # Second call should hit the cache
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
        
        # Cache user data
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
        
        # Cache guessed names
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