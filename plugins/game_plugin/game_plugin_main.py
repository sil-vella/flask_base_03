from tools.logger.custom_logging import custom_log

from plugins.game_plugin.modules.function_helper_module.function_helper_module import FunctionHelperModule
from plugins.game_plugin.modules.game_state_module.state_manager import StateManager
from plugins.game_plugin.modules.game_events_module.event_handlers import GameEventHandlers
from plugins.game_plugin.modules.game_events_module.event_validators import GameEventValidators
from plugins.game_plugin.modules.game_rules_module.rules_engine import GameRulesEngine
from plugins.game_plugin.modules.game_rules_module.action_validator import GameActionValidator


class GamePlugin:
    def initialize(self, app_manager):
        """
        Initialize the GamePlugin with AppManager.
        :param app_manager: AppManager - The main application manager.
        """
        custom_log("Initializing GamePlugin...")

        try:
            # First, ensure ConnectionAPI is available
            connection_api = app_manager.module_manager.get_module("connection_api")
            if not connection_api:
                raise RuntimeError("ConnectionAPI is not registered in ModuleManager.")

            # Register function helper module
            app_manager.module_manager.register_module(
                "function_helper_module", 
                FunctionHelperModule, 
                app_manager=app_manager
            )
            
            # Register state management module
            app_manager.module_manager.register_module(
                "game_state_module",
                StateManager,
                redis_manager=app_manager.websocket_manager.redis_manager
            )
            
            # Register rules engine module
            app_manager.module_manager.register_module(
                "game_rules_engine",
                GameRulesEngine,
                state_manager=app_manager.module_manager.get_module("game_state_module")
            )
            
            # Register action validator module
            app_manager.module_manager.register_module(
                "game_action_validator",
                GameActionValidator
            )
            
            # Register event validators module
            app_manager.module_manager.register_module(
                "game_event_validators",
                GameEventValidators,
                state_manager=app_manager.module_manager.get_module("game_state_module")
            )
            
            # Register event handlers module
            app_manager.module_manager.register_module(
                "game_event_handlers",
                GameEventHandlers,
                None,  # app_manager is not needed for GameEventHandlers
                app_manager.websocket_manager,
                app_manager.module_manager.get_module("game_state_module"),
                app_manager.module_manager.get_module("game_rules_engine"),
                app_manager.module_manager.get_module("game_action_validator"),
                app_manager.module_manager.get_module("game_event_validators")
            )

            custom_log("GamePlugin initialized successfully")

        except Exception as e:
            custom_log(f"Error initializing GamePlugin: {e}")
            raise