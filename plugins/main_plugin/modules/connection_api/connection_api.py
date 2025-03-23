import psycopg2
import psycopg2.extras
import os
from tools.logger.custom_logging import custom_log, log_function_call

class ConnectionAPI:
    def __init__(self, app_manager=None):
        self.registered_routes = []
        self.app = None  # Reference to Flask app
        self.db_connection = self.connect_to_db()  # Initialize DB connection
        self.app_manager = app_manager  # Reference to AppManager if provided

        # ✅ Ensure tables exist in the database
        self.initialize_database()

    def initialize(self, app):
        """Initialize the ConnectionAPI with a Flask app."""
        if not hasattr(app, "add_url_rule"):
            raise RuntimeError("ConnectionAPI requires a valid Flask app instance.")
        self.app = app

    def connect_to_db(self):
        """Establish a connection to the database and return the connection object."""
        try:
            # Read password from secret file
            with open(os.getenv("POSTGRES_PASSWORD_FILE"), 'r') as f:
                db_password = f.read().strip()

            connection = psycopg2.connect(
                user=os.getenv("POSTGRES_USER"),
                password=db_password,
                host=os.getenv("DB_HOST", "127.0.0.1"),
                port=os.getenv("DB_PORT", "5432"),
                database=os.getenv("POSTGRES_DB")
            )
            custom_log("✅ Database connection established")
            return connection
        except Exception as e:
            custom_log(f"❌ Error connecting to database: {e}")
            return None

    def get_connection(self):
        """Retrieve an active database connection."""
        if self.db_connection is None or self.db_connection.closed:
            custom_log("🔄 Reconnecting to database...")
            self.db_connection = self.connect_to_db()

        # ✅ Ensure autocommit mode is enabled
        self.db_connection.autocommit = True  # Prevents transaction blocks from lingering

        return self.db_connection


    def fetch_from_db(self, query, params=None, as_dict=False):
        """Execute a SELECT query and return results while handling transaction errors properly."""
        try:
            connection = self.get_connection()
            cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor if as_dict else None)
            
            cursor.execute(query, params or ())
            result = cursor.fetchall()
            cursor.close()
            
            return [dict(row) for row in result] if as_dict else result
        except psycopg2.Error as e:
            custom_log(f"❌ Database error in SELECT: {e}")
            connection.rollback()  # ✅ Ensure transaction rollback on error
            return None


    def execute_query(self, query, params=None):
        """Execute INSERT, UPDATE, or DELETE queries and properly handle transactions."""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute(query, params or ())
            connection.commit()  # ✅ Commit the transaction
            cursor.close()
            
            custom_log("✅ Query executed successfully")
        except psycopg2.Error as e:
            custom_log(f"❌ Error executing query: {e}")
            connection.rollback()  # ✅ Rollback in case of failure


    def initialize_database(self):
        """Ensure required tables exist in the database."""
        custom_log("⚙️ Initializing database tables...")

        self._create_users_table()
        self._create_user_category_progress_table()
        self._create_guessed_names_table()

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

    def _create_user_category_progress_table(self):
        """Create table to track user levels and points per category and level."""
        query = """
        CREATE TABLE IF NOT EXISTS user_category_progress (
            id SERIAL PRIMARY KEY,
            user_id INT NOT NULL,
            category VARCHAR(50) NOT NULL,
            level INT NOT NULL,
            points INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (user_id, category, level)
        );
        """
        self.execute_query(query)
        custom_log("✅ User category progress table verified.")

    def _create_guessed_names_table(self):
        """Create guessed_names table if it doesn't exist."""
        query = """
        CREATE TABLE IF NOT EXISTS guessed_names (
            id SERIAL PRIMARY KEY,
            user_id INT NOT NULL,
            category VARCHAR(50) NOT NULL,
            level INT NOT NULL DEFAULT 1,
            guessed_name VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (user_id, category, level, guessed_name)
        );
        """
        self.execute_query(query)
        custom_log("✅ Guessed names table verified.")

    def add_guessed_name(self, user_id, category, level, guessed_name):
        """Add a guessed name for a specific user, category, and level."""
        query = """
        INSERT INTO guessed_names (user_id, category, level, guessed_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, category, level, guessed_name) DO NOTHING;
        """
        self.execute_query(query, (user_id, category, level, guessed_name))

    def get_guessed_names(self, user_id, category, level):
        """Retrieve guessed names for a user in a specific category and level."""
        query = "SELECT guessed_name FROM guessed_names WHERE user_id = %s AND category = %s AND level = %s"
        results = self.fetch_from_db(query, (user_id, category, level), as_dict=True)
        return [row['guessed_name'] for row in results] if results else []

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
        if self.db_connection:
            self.db_connection.close()
            custom_log("🔌 Database connection closed.")

    def get_all_user_data(self, user_id):
        """Retrieve all user data including profile, category progress, and guessed names."""
        try:
            user_query = "SELECT id, username, email, total_points, created_at FROM users WHERE id = %s"
            user_data = self.fetch_from_db(user_query, (user_id,), as_dict=True)

            if not user_data:
                return {"error": f"User with ID {user_id} not found"}, 404

            user_info = user_data[0]

            progress_query = """
            SELECT category, level, points FROM user_category_progress WHERE user_id = %s
            """
            progress_data = self.fetch_from_db(progress_query, (user_id,), as_dict=True)

            category_progress = {row["category"]: {row["level"]: {"points": row["points"]}} for row in progress_data}

            guessed_query = """
            SELECT category, level, guessed_name FROM guessed_names WHERE user_id = %s
            """
            guessed_data = self.fetch_from_db(guessed_query, (user_id,), as_dict=True)

            guessed_names = {row["category"]: {row["level"]: [row["guessed_name"]]} for row in guessed_data}

            return {
                "user_info": user_info,
                "category_progress": category_progress,
                "guessed_names": guessed_names,
                "total_points": user_info["total_points"]
            }, 200

        except Exception as e:
            custom_log(f"❌ Error fetching user data: {e}")
            return {"error": f"Server error: {str(e)}"}, 500
