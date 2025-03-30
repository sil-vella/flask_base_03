from flask import request
from core.managers.websocket_manager import WebSocketManager
from core.managers.redis_manager import RedisManager
from core.managers.jwt_manager import JWTManager, TokenType
from tools.logger.custom_logging import custom_log
from typing import Dict, Any, Optional
from flask_cors import CORS
import time
import os
from datetime import datetime, timedelta
from utils.config.config import Config

class WebSocketModule:
    def __init__(self, app_manager=None):
        self.app_manager = app_manager
        self.websocket_manager = WebSocketManager()
        self.redis_manager = RedisManager()
        self.jwt_manager = JWTManager()  # Initialize JWT manager
        
        # Set JWT manager in WebSocket manager
        self.websocket_manager.set_jwt_manager(self.jwt_manager)
        
        if app_manager and app_manager.flask_app:
            self.websocket_manager.initialize(app_manager.flask_app)
        
        # Initialize CORS settings
        self._setup_cors()
        
        self._register_handlers()
        self.button_counter_room = "button_counter_room"
        custom_log("WebSocketModule initialized")

    def _setup_cors(self):
        """Configure CORS settings with security measures."""
        # Use allowed origins from Config
        allowed_origins = Config.WS_ALLOWED_ORIGINS
        
        # Configure CORS with specific origins
        self.websocket_manager.set_cors_origins(allowed_origins)
        custom_log(f"WebSocket CORS configured for origins: {allowed_origins}")

    def _register_handlers(self):
        """Register all WebSocket event handlers."""
        # Connect and disconnect don't use authentication
        self.websocket_manager.register_handler('connect', self._handle_connect)
        self.websocket_manager.register_handler('disconnect', self._handle_disconnect)
        
        # All other handlers use authentication
        self.websocket_manager.register_authenticated_handler('join', self._handle_join)
        self.websocket_manager.register_authenticated_handler('leave', self._handle_leave)
        self.websocket_manager.register_authenticated_handler('message', self._handle_message)
        self.websocket_manager.register_authenticated_handler('button_press', self._handle_button_press)
        self.websocket_manager.register_authenticated_handler('get_counter', self._handle_get_counter)
        custom_log("WebSocket event handlers registered")

    def _validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate JWT token and return user data if valid."""
        try:
            # Validate the token
            payload = self.jwt_manager.verify_token(token, TokenType.ACCESS)
            if not payload:
                return None
                
            # Get user data from Redis cache
            user_data = self.redis_manager.get(f"user:{payload['user_id']}")
            if not user_data:
                return None
                
            return user_data
        except Exception as e:
            custom_log(f"Token validation error: {str(e)}")
            return None

    def _handle_connect(self, data=None):
        """Handle new WebSocket connections with security checks."""
        session_id = request.sid
        origin = request.headers.get('Origin', '')
        client_id = request.headers.get('X-Client-ID', session_id)
        token = request.args.get('token')  # Get token from query parameters
        
        # For testing, allow all origins
        if origin == 'null' or not origin:
            origin = 'http://localhost:5000'
            
        # Validate origin
        if not self.websocket_manager.validate_origin(origin):
            custom_log(f"Invalid origin rejected: {origin}")
            return {'status': 'error', 'message': 'Invalid origin'}
            
        # Check rate limits
        if not self.websocket_manager.check_rate_limit(client_id, 'connections'):
            custom_log(f"Rate limit exceeded for client: {client_id}")
            return {'status': 'error', 'message': 'Rate limit exceeded'}
            
        # Validate JWT token
        if not token:
            custom_log("No token provided for WebSocket connection")
            return {'status': 'error', 'message': 'Authentication required'}
            
        user_data = self._validate_token(token)
        if not user_data:
            custom_log("Invalid token for WebSocket connection")
            return {'status': 'error', 'message': 'Invalid authentication'}
            
        # Update rate limits
        self.websocket_manager.update_rate_limit(client_id, 'connections')
        
        # Store session info with user data
        session_data = {
            'client_id': client_id,
            'origin': origin,
            'user_id': user_data['id'],
            'connected_at': datetime.utcnow().isoformat(),
            'last_active': datetime.utcnow().isoformat()
        }
        self.websocket_manager.store_session_data(session_id, session_data)
        
        # Join button counter room
        self.websocket_manager.join_room(self.button_counter_room, session_id)
        
        custom_log(f"New WebSocket connection: {session_id} from {origin} for user {user_data['id']}")
        return {'status': 'connected', 'session_id': session_id}

    def _handle_disconnect(self, data=None):
        """Handle WebSocket disconnections with cleanup."""
        session_id = request.sid
        
        # Clean up session data
        self.websocket_manager.cleanup_session_data(session_id)
        
        # Clean up WebSocket session
        self.websocket_manager.cleanup_session(session_id)
        custom_log(f"WebSocket disconnected: {session_id}")

    def _handle_join(self, data: Dict[str, Any], session_data: Dict[str, Any]):
        """Handle joining a room with authentication."""
        session_id = request.sid
        room_id = data.get('room_id')
        if not room_id:
            raise ValueError("room_id is required")
        
        self.websocket_manager.join_room(room_id, session_id)
        return {'status': 'joined', 'room_id': room_id}

    def _handle_leave(self, data: Dict[str, Any], session_data: Dict[str, Any]):
        """Handle leaving a room with authentication."""
        session_id = request.sid
        room_id = data.get('room_id')
        if not room_id:
            raise ValueError("room_id is required")
        
        self.websocket_manager.leave_room(room_id, session_id)
        return {'status': 'left', 'room_id': room_id}

    def _handle_message(self, data: Dict[str, Any], session_data: Dict[str, Any]):
        """Handle incoming messages with authentication."""
        session_id = request.sid
        message = data.get('message')
        room_id = data.get('room_id')
        
        if not message:
            raise ValueError("message is required")
            
        # Check rate limits for messages
        if not self.websocket_manager.check_rate_limit(session_data['client_id'], 'messages'):
            return {'status': 'error', 'message': 'Rate limit exceeded'}
            
        # Update rate limits
        self.websocket_manager.update_rate_limit(session_data['client_id'], 'messages')
        
        # Broadcast message to room or all connected clients
        if room_id:
            self.websocket_manager.broadcast_to_room(room_id, 'message', {
                'message': message,
                'user_id': session_data['user_id'],
                'timestamp': datetime.utcnow().isoformat()
            })
        else:
            self.websocket_manager.broadcast_to_all('message', {
                'message': message,
                'user_id': session_data['user_id'],
                'timestamp': datetime.utcnow().isoformat()
            })
            
        return {'status': 'sent'}

    def _handle_button_press(self, data: Dict[str, Any]):
        """Handle button press events."""
        session_id = request.sid
        
        # Update counter in Redis
        counter_key = f"button_counter:{self.button_counter_room}"
        current_count = self.redis_manager.incr(counter_key)
        
        # Broadcast updated count to room
        self.websocket_manager.broadcast_to_room(
            self.button_counter_room,
            'counter_update',
            {'count': current_count}
        )
        
        return {'status': 'success', 'count': current_count}

    def _handle_get_counter(self, data: Dict[str, Any]):
        """Handle getting the current counter value."""
        counter_key = f"button_counter:{self.button_counter_room}"
        current_count = self.redis_manager.get(counter_key) or 0
        return {'status': 'success', 'count': current_count}

    def broadcast_to_room(self, room_id: str, event: str, data: Any):
        """Broadcast message to a specific room."""
        self.websocket_manager.broadcast_to_room(room_id, event, data)

    def send_to_session(self, session_id: str, event: str, data: Any):
        """Send message to a specific session."""
        self.websocket_manager.send_to_session(session_id, event, data)

    def get_room_members(self, room_id: str) -> set:
        """Get all members in a room."""
        return self.websocket_manager.get_room_members(room_id)

    def get_rooms_for_session(self, session_id: str) -> set:
        """Get all rooms for a session."""
        return self.websocket_manager.get_rooms_for_session(session_id)