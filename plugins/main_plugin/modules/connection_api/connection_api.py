import psycopg2
import psycopg2.extras
import psycopg2.pool
import os
import json
from tools.logger.custom_logging import custom_log, log_function_call
from utils.config.config import Config
from core.managers.redis_manager import RedisManager
from tools.error_handling import ErrorHandler
from datetime import datetime
import time
import uuid
import logging

class ConnectionAPI:
    def __init__(self, app_manager=None):
        """Initialize the ConnectionAPI with Redis and database connections."""
        self.registered_routes = []
        self.app = None  # Reference to Flask app
        self.app_manager = app_manager  # Reference to AppManager if provided
        self.connection_pool = self._create_connection_pool()  # Initialize PostgreSQL connection pool
        self.redis_manager = RedisManager()  # Initialize Redis manager
        self.error_handler = ErrorHandler()  # Initialize error handler
        self.logger = logging.getLogger(__name__)
        
        # Session management settings
        self.session_timeout = 3600  # 1 hour in seconds
        self.max_concurrent_sessions = 3  # Maximum concurrent sessions per user
        self.session_check_interval = 300  # 5 minutes in seconds

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
                    connection_state,
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
                    {
                        "status": "returned",
                        "returned_at": str(datetime.now().isoformat())
                    },
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
            # Validate query type and format
            if not query or not isinstance(query, str):
                raise ValueError("Invalid query format")
                
            # Validate query is SELECT
            if not query.strip().upper().startswith('SELECT'):
                raise ValueError("Only SELECT queries are allowed in fetch_from_db")
                
            # Validate parameters
            if params is not None:
                if not isinstance(params, (tuple, list)):
                    raise ValueError("Parameters must be a tuple or list")
                if any(not isinstance(p, (str, int, float, bool, type(None))) for p in params):
                    raise ValueError("Invalid parameter types")

            # Validate query size
            if not self.error_handler.validate_query_size(query, params):
                error_response = self.error_handler.handle_validation_error(
                    ValueError("Query size exceeds maximum allowed size")
                )
                raise ValueError(error_response["error"])

            connection = self.get_connection()
            cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor if as_dict else None)
            
            # Create cache key based on query and parameters
            cache_key = f"query:{hash(query + str(params or ()))}"
            
            # Try to get from Redis cache first
            try:
                cached_result = self.redis_manager.get(cache_key)
                if cached_result:
                    custom_log(f"✅ Retrieved query result from Redis cache")
                    # Convert list of lists back to list of tuples for non-dict results
                    if not as_dict:
                        cached_result = [tuple(row) for row in cached_result]
                    return cached_result
            except Exception as e:
                error_response = self.error_handler.handle_redis_error(e, "cache_get")
                custom_log(f"⚠️ Cache retrieval failed: {error_response['error']}")
            
            cursor.execute(query, params or ())
            result = cursor.fetchall()
            cursor.close()
            
            # Convert to dict if requested
            if as_dict:
                processed_result = [dict(row) for row in result]
            else:
                processed_result = [tuple(row) for row in result]
            
            # Validate result size before caching
            MAX_RESULT_SIZE = 1024 * 1024  # 1MB
            result_size = len(json.dumps(processed_result))
            if result_size > MAX_RESULT_SIZE:
                custom_log("⚠️ Query result too large for caching")
                return processed_result
            
            # Cache the result
            try:
                self.redis_manager.set(cache_key, processed_result, expire=300)  # Cache for 5 minutes
                custom_log(f"✅ Cached query result in Redis")
            except Exception as e:
                error_response = self.error_handler.handle_redis_error(e, "cache_set")
                custom_log(f"⚠️ Cache storage failed: {error_response['error']}")
            
            return processed_result
            
        except Exception as e:
            error_response = self.error_handler.handle_database_error(e, "fetch_from_db")
            custom_log(f"❌ Error executing query: {error_response['error']}")
            raise ValueError(error_response["error"])
        finally:
            if connection:
                self.return_connection(connection)

    def execute_query(self, query, params=None):
        """Execute a non-SELECT query and invalidate relevant caches."""
        connection = None
        try:
            # Validate query size
            if not self.error_handler.validate_query_size(query, params):
                error_response = self.error_handler.handle_validation_error(
                    ValueError("Query size exceeds maximum allowed size")
                )
                raise ValueError(error_response["error"])

            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute(query, params or ())
            connection.commit()
            cursor.close()
            
            # Invalidate relevant caches
            self._invalidate_caches(query)
            
        except Exception as e:
            if connection:
                connection.rollback()
            error_response = self.error_handler.handle_database_error(e, "execute_query")
            custom_log(f"❌ Error executing query: {error_response['error']}")
            raise ValueError(error_response["error"])
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
        """Cache user data in Redis with encryption."""
        # Validate user_id
        if not isinstance(user_id, (int, str)) or not str(user_id).isdigit():
            raise ValueError("Invalid user_id")
        
        # Validate data structure
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")
        
        # Validate required fields
        required_fields = ['id', 'username', 'email']
        if not all(field in data for field in required_fields):
            raise ValueError("Missing required user data fields")
        
        # Validate data size
        data_size = len(json.dumps(data))
        if data_size > 1024 * 1024:  # 1MB limit
            raise ValueError("User data too large for caching")
        
        # Validate data types
        if not isinstance(data['id'], (int, str)) or not str(data['id']).isdigit():
            raise ValueError("Invalid user ID in data")
        if not isinstance(data['username'], str) or len(data['username']) > 50:
            raise ValueError("Invalid username format")
        if not isinstance(data['email'], str) or '@' not in data['email']:
            raise ValueError("Invalid email format")
        
        self.redis_manager.set(f"user:{user_id}", data, expire=3600)  # Cache for 1 hour

    def get_cached_user_data(self, user_id):
        """Get cached user data from Redis with decryption."""
        # Validate user_id
        if not isinstance(user_id, (int, str)) or not str(user_id).isdigit():
            raise ValueError("Invalid user_id")
        
        # Get cached data
        data = self.redis_manager.get(f"user:{user_id}")
        
        # Validate cached data structure
        if data:
            if not isinstance(data, dict):
                self.redis_manager.delete(f"user:{user_id}")  # Clear invalid data
                return None
                
            # Validate required fields
            required_fields = ['id', 'username', 'email']
            if not all(field in data for field in required_fields):
                self.redis_manager.delete(f"user:{user_id}")  # Clear invalid data
                return None
                
            # Validate data types
            if not isinstance(data['id'], (int, str)) or not str(data['id']).isdigit():
                self.redis_manager.delete(f"user:{user_id}")  # Clear invalid data
                return None
        
        return data

    @property
    def redis(self):
        """Access Redis manager methods directly."""
        return self.redis_manager

    def _invalidate_caches(self, query):
        """Invalidate relevant Redis caches based on the query."""
        query = query.lower()
        
        # Invalidate query cache
        cache_key = f"query:{hash(query)}"
        self.redis_manager.delete(cache_key)
        
        # Invalidate user data cache if user-related query
        if "users" in query:
            pattern = "user:*"
            keys = self.redis_manager.redis.keys(pattern)
            for key in keys:
                self.redis_manager.delete(key)
        
        custom_log("✅ Relevant caches invalidated")

    def _create_session(self, user_id: int) -> str:
        """Create a new session for a user."""
        try:
            # Check concurrent session limit using Redis set
            user_sessions_key = f"user_sessions:{user_id}"
            active_session_count = self.redis_manager.redis.scard(user_sessions_key)
            
            if active_session_count >= self.max_concurrent_sessions:
                raise ValueError(f"Maximum concurrent sessions ({self.max_concurrent_sessions}) reached for user {user_id}")
            
            # Generate session ID
            session_id = f"session:{user_id}:{uuid.uuid4().hex}"
            
            # Create session data
            session_data = {
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
                "ip_address": None,  # To be set by web layer
                "user_agent": None   # To be set by web layer
            }
            
            # Store session in Redis
            self.redis_manager.redis.setex(
                session_id,
                self.session_timeout,
                json.dumps(session_data)
            )
            
            # Add to user's active sessions using Redis set
            self.redis_manager.redis.sadd(user_sessions_key, session_id)
            
            self.logger.info(f"Created new session {session_id} for user {user_id}")
            return session_id
            
        except Exception as e:
            self.logger.error(f"Failed to create session for user {user_id}: {str(e)}")
            raise

    def _get_active_sessions(self, user_id):
        """Get all active sessions for a user."""
        try:
            # Get all session keys for the user
            pattern = f"session:{user_id}:*"
            session_keys = self.redis_manager.redis.keys(pattern)
            
            active_sessions = []
            current_time = datetime.utcnow()
            
            for key in session_keys:
                session_data = self.redis_manager.redis.get(key)
                if session_data:
                    session_data = json.loads(session_data)
                    # Parse last activity time from ISO format
                    last_activity = datetime.fromisoformat(session_data["last_activity"])
                    
                    # Check if session is still active
                    if (current_time - last_activity).total_seconds() < self.session_timeout:
                        active_sessions.append(session_data)
                    else:
                        # Clean up expired session
                        self.redis_manager.redis.delete(key)
                        # Also remove from user's sessions set
                        self.redis_manager.redis.srem(f"user_sessions:{user_id}", key)
            
            return active_sessions
        except Exception as e:
            error_response = self.error_handler.handle_error(e, "get_active_sessions")
            custom_log(f"❌ Error getting active sessions: {error_response['error']}")
            return []

    def _update_session_activity(self, session_id):
        """Update the last activity time of a session."""
        try:
            session_data = self.redis_manager.redis.get(session_id)
            if session_data:
                session_data = json.loads(session_data)
                session_data["last_activity"] = datetime.utcnow().isoformat()
                self.redis_manager.redis.setex(
                    session_id,
                    self.session_timeout,
                    json.dumps(session_data)
                )
                return True
            return False
        except Exception as e:
            error_response = self.error_handler.handle_error(e, "update_session_activity")
            custom_log(f"❌ Error updating session activity: {error_response['error']}")
            return False

    def _validate_session(self, session_id):
        """Validate a session and return session data if valid."""
        try:
            session_data = self.redis_manager.redis.get(session_id)
            if not session_data:
                return None
                
            session_data = json.loads(session_data)
            # Parse last activity time from ISO format
            last_activity = datetime.fromisoformat(session_data["last_activity"])
            current_time = datetime.utcnow()
            
            # Check if session has expired
            if (current_time - last_activity).total_seconds() > self.session_timeout:
                # Session expired
                self.redis_manager.redis.delete(session_id)
                return None
                
            # Update last activity
            session_data["last_activity"] = current_time.isoformat()
            self.redis_manager.redis.setex(
                session_id,
                self.session_timeout,
                json.dumps(session_data)
            )
            
            return session_data
        except Exception as e:
            error_response = self.error_handler.handle_error(e, "validate_session")
            custom_log(f"❌ Error validating session: {error_response['error']}")
            return None

    def _cleanup_expired_sessions(self):
        """Clean up expired sessions for all users."""
        try:
            # Get all session keys
            pattern = "session:*"
            session_keys = self.redis_manager.redis.keys(pattern)
            
            current_time = datetime.utcnow()
            for key in session_keys:
                session_data = self.redis_manager.redis.get(key)
                if session_data:
                    session_data = json.loads(session_data)
                    # Parse last activity time from ISO format
                    last_activity = datetime.fromisoformat(session_data["last_activity"])
                    
                    # Check if session has expired
                    if (current_time - last_activity).total_seconds() > self.session_timeout:
                        # Get user_id from session key
                        user_id = key.split(":")[1]
                        
                        # Delete session
                        self.redis_manager.redis.delete(key)
                        # Also remove from user's sessions set
                        self.redis_manager.redis.srem(f"user_sessions:{user_id}", key)
                        custom_log(f"✅ Cleaned up expired session: {key}")
        except Exception as e:
            error_response = self.error_handler.handle_error(e, "cleanup_expired_sessions")
            custom_log(f"❌ Error cleaning up expired sessions: {error_response['error']}")

    def _terminate_session(self, session_id):
        """Terminate a specific session."""
        try:
            # Get user_id from session key
            user_id = session_id.split(":")[1]
            
            # Delete session
            self.redis_manager.redis.delete(session_id)
            # Also remove from user's sessions set
            self.redis_manager.redis.srem(f"user_sessions:{user_id}", session_id)
            custom_log(f"✅ Terminated session: {session_id}")
        except Exception as e:
            error_response = self.error_handler.handle_error(e, "terminate_session")
            custom_log(f"❌ Error terminating session: {error_response['error']}")

    def _terminate_user_sessions(self, user_id):
        """Terminate all sessions for a user."""
        try:
            pattern = f"session:{user_id}:*"
            session_keys = self.redis_manager.redis.keys(pattern)
            for key in session_keys:
                # Delete session
                self.redis_manager.redis.delete(key)
                # Also remove from user's sessions set
                self.redis_manager.redis.srem(f"user_sessions:{user_id}", key)
            custom_log(f"✅ Terminated all sessions for user: {user_id}")
        except Exception as e:
            error_response = self.error_handler.handle_error(e, "terminate_user_sessions")
            custom_log(f"❌ Error terminating user sessions: {error_response['error']}")

    def _get_session_info(self, session_id):
        """Get detailed information about a session."""
        try:
            session_data = self.redis_manager.redis.get(session_id)
            if not session_data:
                return None
                
            session_data = json.loads(session_data)
            return {
                "session_id": session_id,
                "user_id": session_data["user_id"],
                "created_at": session_data["created_at"],
                "last_activity": session_data["last_activity"],
                "timeout": self.session_timeout,
                "ip_address": session_data.get("ip_address"),
                "user_agent": session_data.get("user_agent")
            }
        except Exception as e:
            error_response = self.error_handler.handle_error(e, "get_session_info")
            custom_log(f"❌ Error getting session info: {error_response['error']}")
            return None
