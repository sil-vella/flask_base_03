from flask import request, jsonify
from tools.logger.custom_logging import custom_log
from core.managers.module_manager import ModuleManager

class LeaderboardModule:
    def __init__(self, app_manager=None):
        """Initialize LeaderboardModule and register routes."""
        self.app_manager = app_manager
        self.connection_module = self.get_connection_module()

        if not self.connection_module:
            raise RuntimeError("LeaderboardModule: Failed to retrieve ConnectionModule from ModuleManager.")

        custom_log("✅ LeaderboardModule initialized.")
        self.register_routes()

    def get_connection_module(self):
        """Retrieve ConnectionModule from ModuleManager."""
        module_manager = self.app_manager.module_manager if self.app_manager else ModuleManager()
        return module_manager.get_module("connection_module")

    def register_routes(self):
        """Register leaderboard route."""
        if not self.connection_module:
            raise RuntimeError("ConnectionModule is not available yet.")

        self.connection_module.register_route('/get-leaderboard', self.get_leaderboard, methods=['GET'])
        custom_log("🌐 LeaderboardModule: `/get-leaderboard` route registered.")

    def get_leaderboard(self):
        """Retrieve the leaderboard and optionally include the user's rank."""
        try:
            connection = self.connection_module.get_connection()

            # ✅ Retrieve top 10 users ordered by points using DENSE_RANK
            leaderboard_query = """
            SELECT username, total_points AS points,
                DENSE_RANK() OVER (ORDER BY total_points DESC) AS rank
            FROM users
            ORDER BY total_points DESC
            LIMIT 10;
            """
            leaderboard_data = self.connection_module.fetch_from_db(leaderboard_query, as_dict=True) or []

            # ✅ Get the user's rank if an email is provided
            user_email = request.args.get("email")
            user_rank = None

            if user_email:
                user_rank_query = """
                SELECT username, total_points AS points,
                    DENSE_RANK() OVER (ORDER BY total_points DESC) AS rank
                FROM users
                WHERE email = %s;
                """
                user_rank_data = self.connection_module.fetch_from_db(user_rank_query, (user_email,), as_dict=True)

                if user_rank_data:
                    user_rank = user_rank_data[0]
                else:
                    user_rank = None  # ✅ Explicitly set None if user has no rank

            # ✅ Ensure leaderboard always returns data
            response = {
                "leaderboard": leaderboard_data,
                "user_rank": user_rank
            }

            return jsonify(response), 200

        except Exception as e:
            custom_log(f"❌ Error retrieving leaderboard: {e}")
            return jsonify({"error": "Server error retrieving leaderboard"}), 500
