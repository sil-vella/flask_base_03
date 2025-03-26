import psycopg2
import psycopg2.extras
import psycopg2.pool
import os
import json
from tools.logger.custom_logging import custom_log, log_function_call
from utils.config.config import Config
from core.managers.redis_manager import RedisManager
from datetime import datetime
import time

class ConnectionAPI:
    def __init__(self, app_manager=None):
        self.registered_routes = []
        self.app = None  # Reference to Flask app
        self.app_manager = app_manager  # Reference to AppManager if provided
        self.connection_pool = self._create_connection_pool()  # Initialize PostgreSQL connection pool
        self.redis_manager = RedisManager()  # Initialize Redis manager

        # ✅ Ensure tables exist in the database
        self.initialize_database()

    def initialize(self, app):
        """Initialize the ConnectionAPI with a Flask app."""
        if not hasattr(app, "add_url_rule"):
            raise RuntimeError("ConnectionAPI requires a valid Flask app instance.")
        self.app = app

    def _create_connection_pool(self):
        """Create a PostgreSQL connection pool with security features."""
        try:
            # Get database credentials from environment
            db_host = os.getenv("POSTGRES_HOST", "localhost")
            db_port = os.getenv("POSTGRES_PORT", "5432")
            db_name = os.getenv("POSTGRES_DB", "postgres")
            db_user = os.getenv("POSTGRES_USER", "postgres")
            
            # Get password from file or environment variable
            password_file = os.getenv("POSTGRES_PASSWORD_FILE")
            if password_file and os.path.exists(password_file):
                with open(password_file, 'r') as f:
                    db_password = f.read().strip()
            else:
                db_password = os.getenv("POSTGRES_PASSWORD")
            
            if not db_password:
                raise ValueError("Database password not found in file or environment variable")

            # Connection parameters with security features
            connection_params = {
                "host": db_host,
                "port": db_port,
                "database": db_name,
                "user": db_user,
                "password": db_password,
                "connect_timeout": Config.DB_CONNECT_TIMEOUT,
                "keepalives": Config.DB_KEEPALIVES,
                "keepalives_idle": Config.DB_KEEPALIVES_IDLE,
                "keepalives_interval": Config.DB_KEEPALIVES_INTERVAL,
                "keepalives_count": Config.DB_KEEPALIVES_COUNT,
                "application_name": "template_three_app"
            }

            # Add SSL if enabled
            if Config.USE_SSL:
                connection_params["sslmode"] = "require"

            # Create connection pool with security features
            pool = psycopg2.pool.SimpleConnectionPool(
                minconn=Config.DB_POOL_MIN_CONN,
                maxconn=Config.DB_POOL_MAX_CONN,
                **connection_params
            )

            # Test the pool with a health check
            with pool.getconn() as conn:
                with conn.cursor() as cur:
                    # Set statement timeout for this connection
                    cur.execute(f"SET statement_timeout = {Config.DB_STATEMENT_TIMEOUT}")
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    if not result or result[0] != 1:
                        raise RuntimeError("Health check failed")

            custom_log(f"✅ Database connection pool created successfully with security features. Pool size: {Config.DB_POOL_MIN_CONN}-{Config.DB_POOL_MAX_CONN}")
            return pool

        except Exception as e:
            custom_log(f"❌ Error creating connection pool: {e}")
            raise RuntimeError(f"Failed to create database connection pool: {str(e)}")

    def get_connection(self):
        """Get a connection from the pool with retry logic and state tracking."""
        retry_count = 0
        last_error = None

        while retry_count < Config.DB_RETRY_COUNT:
            try:
                # Check if pool exists, if not create it
                if not self.connection_pool:
                    self.connection_pool = self._create_connection_pool()

                # Get connection from pool with timeout
                conn = self.connection_pool.getconn()
                if not conn:
                    raise RuntimeError("Failed to get connection from pool")

                # Set statement timeout for this connection
                with conn.cursor() as cur:
                    cur.execute(f"SET statement_timeout = {Config.DB_STATEMENT_TIMEOUT}")

                # Track connection state in Redis
                connection_id = id(conn)
                connection_state = {
                    "created_at": time.time(),
                    "status": "active",
                    "statement_timeout": Config.DB_STATEMENT_TIMEOUT,
                    "last_used": time.time()
                }
                
                # Cache connection state with expiration
                self.redis_manager.set(
                    f"connection:{connection_id}",
                    json.dumps(connection_state),
                    expire=Config.DB_KEEPALIVES_IDLE * 2
                )

                custom_log(f"✅ Got connection from pool (ID: {connection_id})")
                return conn

            except (psycopg2.OperationalError, RuntimeError) as e:
                last_error = e
                retry_count += 1
                custom_log(f"Connection attempt {retry_count} failed: {str(e)}")
                
                if retry_count < Config.DB_RETRY_COUNT:
                    time.sleep(Config.DB_RETRY_DELAY)
                    continue
                
                # If we've exhausted retries, try to recreate the pool
                custom_log("Max retries reached, attempting to recreate connection pool")
                self.connection_pool = self._create_connection_pool()
                retry_count = 0  # Reset retry count after pool recreation
                time.sleep(Config.DB_RETRY_DELAY)

            except Exception as e:
                custom_log(f"Unexpected error getting connection: {str(e)}")
                raise

        # If we get here, all retries failed
        raise RuntimeError(f"Failed to get connection after {Config.DB_RETRY_COUNT} attempts. Last error: {str(last_error)}")

    def return_connection(self, connection):
        """Return a connection to the pool and update Redis cache."""
        if self.connection_pool is not None and connection is not None:
            try:
                conn_id = id(connection)
                # Update connection state in Redis
                self.redis_manager.set(
                    f"connection:{conn_id}",
                    json.dumps({
                        "status": "returned",
                        "returned_at": str(datetime.now().isoformat())
                    }),
                    expire=Config.DB_KEEPALIVES_IDLE * 2
                )
                
                self.connection_pool.putconn(connection)
                custom_log(f"✅ Returned connection to pool (ID: {conn_id})")
            except Exception as e:
                custom_log(f"❌ Error returning connection to pool: {e}")

    def fetch_from_db(self, query, params=None, as_dict=False):
        """Execute a SELECT query and cache results in Redis."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor if as_dict else None)
            
            # Create cache key based on query and parameters
            cache_key = f"query:{hash(query + str(params or ()))}"
            
            # Try to get from Redis cache first
            cached_result = self.redis_manager.get(cache_key)
            if cached_result:
                custom_log(f"✅ Retrieved query result from Redis cache")
                result = json.loads(cached_result)
                # Convert list of lists back to list of tuples for non-dict results
                if not as_dict:
                    result = [tuple(row) for row in result]
                return result
            
            cursor.execute(query, params or ())
            result = cursor.fetchall()
            cursor.close()
            
            # Convert to dict if requested
            if as_dict:
                processed_result = [dict(row) for row in result]
            else:
                # Convert tuples to lists for JSON serialization
                processed_result = [list(row) for row in result]
            
            # Cache the result in Redis for 5 minutes
            self.redis_manager.set(cache_key, json.dumps(processed_result), expire=300)
            custom_log(f"✅ Cached query result in Redis")
            
            # Return original format
            if not as_dict:
                result = [tuple(row) for row in processed_result]
                return result
            return processed_result
        except psycopg2.Error as e:
            custom_log(f"❌ Database error in SELECT: {e}")
            if connection:
                connection.rollback()
            return None
        finally:
            if connection:
                self.return_connection(connection)

    def execute_query(self, query, params=None):
        """Execute INSERT, UPDATE, or DELETE queries and invalidate relevant caches."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute(query, params or ())
            connection.commit()
            cursor.close()
            
            # Invalidate any cached results for this query
            cache_key = f"query:{hash(query + str(params or ()))}"
            self.redis_manager.delete(cache_key)
            
            custom_log("✅ Query executed successfully")
        except psycopg2.Error as e:
            custom_log(f"❌ Error executing query: {e}")
            if connection:
                connection.rollback()
        finally:
            if connection:
                self.return_connection(connection)

    def initialize_database(self):
        """Ensure required tables exist in the database."""
        custom_log("⚙️ Initializing database tables...")
        self._create_users_table()
        custom_log("✅ Database tables verified.")

    def _create_users_table(self):
        """Create users table if it doesn't exist."""
        query = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password TEXT NOT NULL,
            total_points INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        self.execute_query(query)
        custom_log("✅ Users table verified.")

    def register_route(self, path, view_func, methods=None, endpoint=None):
        """Register a route with the Flask app."""
        if self.app is None:
            raise RuntimeError("ConnectionAPI must be initialized with a Flask app before registering routes.")

        methods = methods or ["GET"]
        endpoint = endpoint or view_func.__name__

        self.app.add_url_rule(path, endpoint=endpoint, view_func=view_func, methods=methods)
        self.registered_routes.append((path, methods))
        custom_log(f"🌐 Route registered: {path} [{', '.join(methods)}] as '{endpoint}'")

    def dispose(self):
        """Clean up registered routes and resources."""
        custom_log("🔄 Disposing ConnectionAPI...")
        self.registered_routes.clear()
        if self.connection_pool:
            self.connection_pool.closeall()
            custom_log("🔌 Database connection pool closed.")
        if self.redis_manager:
            self.redis_manager.dispose()
            custom_log("🔌 Redis connections closed.")

    def cache_user_data(self, user_id, data):
        """Cache user data in Redis."""
        cache_key = f"user_data:{user_id}"
        self.redis_manager.set(cache_key, json.dumps(data), expire=300)
        custom_log(f"✅ Cached user data for user {user_id}")

    def get_cached_user_data(self, user_id):
        """Get cached user data from Redis."""
        cache_key = f"user_data:{user_id}"
        data = self.redis_manager.get(cache_key)
        if data:
            return json.loads(data)
        return None

    def cache_guessed_names(self, user_id, names):
        """Cache guessed names in Redis."""
        cache_key = f"guessed_names:{user_id}"
        self.redis_manager.set(cache_key, json.dumps(names), expire=300)
        custom_log(f"✅ Cached guessed names for user {user_id}")

    def get_cached_guessed_names(self, user_id):
        """Get cached guessed names from Redis."""
        cache_key = f"guessed_names:{user_id}"
        data = self.redis_manager.get(cache_key)
        if data:
            return json.loads(data)
        return None

    def add_guessed_name(self, user_id, name):
        """Add a guessed name and invalidate relevant caches."""
        query = "INSERT INTO guessed_names (user_id, name) VALUES (%s, %s)"
        self.execute_query(query, (user_id, name))
        
        # Invalidate guessed names cache
        cache_key = f"guessed_names:{user_id}"
        self.redis_manager.delete(cache_key)
        custom_log(f"✅ Added guessed name for user {user_id}")

    @property
    def redis(self):
        """Access Redis manager methods directly."""
        return self.redis_manager
