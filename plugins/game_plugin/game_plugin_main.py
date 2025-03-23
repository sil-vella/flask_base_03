from plugins.game_plugin.modules.question_module.question_module import QuestionModule
from plugins.game_plugin.modules.leaderboard_module.leaderboard_module import LeaderboardModule
from plugins.game_plugin.modules.rewards_module.rewards_module import RewardsModule
from plugins.game_plugin.modules.function_helper_module.function_helper_module import FunctionHelperModule


from tools.logger.custom_logging import custom_log


class GamePlugin:
    def initialize(self, app_manager):
        """
        Initialize the GamePlugin with AppManager.
        :param app_manager: AppManager - The main application manager.
        """
        custom_log("Initializing GamePlugin...")

        try:
            # Ensure QuestionModule is registered FIRST
            if not app_manager.module_manager.get_module("question_module"):
                custom_log("Registering QuestionModule...")
                app_manager.module_manager.register_module(
                    "question_module", 
                    QuestionModule, 
                    app_manager=app_manager
                ),
                app_manager.module_manager.register_module(
                    "leaderboard_module", 
                    LeaderboardModule, 
                    app_manager=app_manager
                ),
                app_manager.module_manager.register_module(
                    "rewards_module", 
                    RewardsModule, 
                    app_manager=app_manager
                ),
                app_manager.module_manager.register_module(
                    "function_helper_module", 
                    FunctionHelperModule, 
                    app_manager=app_manager
                )

        except Exception as e:
            custom_log(f"Error initializing GamePlugin: {e}")
            raise