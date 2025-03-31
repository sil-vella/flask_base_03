from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request
from typing import Dict, Any, Set, Callable, Optional
from tools.logger.custom_logging import custom_log
from core.managers.redis_manager import RedisManager
from core.validators.websocket_validators import WebSocketValidator
from utils.config.config import Config
import time
from datetime import datetime
from functools import wraps

class WebSocketManager:
    def __init__(self):
        self.redis_manager = RedisManager()
        self.validator = WebSocketValidator()
        self.socketio = SocketIO(
            cors_allowed_origins="*",  # Will be overridden by module
            async_mode='gevent',
            logger=True,
            engineio_logger=True,
            max_http_buffer_size=Config.WS_MAX_PAYLOAD_SIZE,
            ping_timeout=Config.WS_PING_TIMEOUT,
            ping_interval=Config.WS_PING_INTERVAL
        )
        self.rooms: Dict[str, Set[str]] = {}  # room_id -> set of session_ids
        self.session_rooms: Dict[str, Set[str]] = {}  # session_id -> set of room_ids
        self._rate_limits = {
            'connections': {
                'max': Config.WS_RATE_LIMIT_CONNECTIONS,
                'window': Config.WS_RATE_LIMIT_WINDOW
            },
            'messages': {
                'max': Config.WS_RATE_LIMIT_MESSAGES,
                'window': Config.WS_RATE_LIMIT_WINDOW
            }
        }
        self._jwt_manager = None  # Will be set by the module
        self._room_access_check = None  # Will be set by the module
        self._room_size_limit = Config.WS_ROOM_SIZE_LIMIT
        self._room_size_check_interval = Config.WS_ROOM_SIZE_CHECK_INTERVAL
        custom_log("WebSocketManager initialized")

    def set_cors_origins(self, origins: list):
        """Set allowed CORS origins."""
        self.socketio.cors_allowed_origins = origins
        custom_log(f"Updated CORS origins: {origins}")

    def validate_origin(self, origin: str) -> bool:
        """Validate if the origin is allowed."""
        return origin in self.socketio.cors_allowed_origins or origin == "app://mobile"

    def check_rate_limit(self, client_id: str, limit_type: str) -> bool:
        """Check if client has exceeded rate limits."""
        if limit_type not in self._rate_limits:
            return True  # Unknown limit type, allow by default
            
        limit = self._rate_limits[limit_type]
        key = f"ws:{limit_type}:{client_id}"
        count = self.redis_manager.get(key) or 0
        
        if count >= limit['max']:
            custom_log(f"Rate limit exceeded for {limit_type}: {client_id}")
            return False
            
        return True

    def update_rate_limit(self, client_id: str, limit_type: str):
        """Update rate limit counter."""
        if limit_type not in self._rate_limits:
            return
            
        limit = self._rate_limits[limit_type]
        key = f"ws:{limit_type}:{client_id}"
        self.redis_manager.incr(key)
        self.redis_manager.expire(key, limit['window'])

    def store_session_data(self, session_id: str, session_data: Dict[str, Any]):
        """Store session information in Redis."""
        self.redis_manager.set(f"ws:session:{session_id}", session_data, expire=Config.WS_SESSION_TTL)

    def get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data from Redis."""
        return self.redis_manager.get(f"ws:session:{session_id}")

    def cleanup_session_data(self, session_id: str):
        """Clean up session data from Redis."""
        self.redis_manager.delete(f"ws:session:{session_id}")

    def update_session_activity(self, session_id: str):
        """Update last active timestamp for session."""
        session_key = f"ws:session:{session_id}"
        session_data = self.redis_manager.get(session_key)
        if session_data:
            session_data['last_active'] = datetime.utcnow().isoformat()
            self.redis_manager.set(session_key, session_data)

    def initialize(self, app):
        """Initialize WebSocket support with the Flask app."""
        self.socketio.init_app(app)
        custom_log("WebSocket support initialized with Flask app")

    def set_jwt_manager(self, jwt_manager):
        """Set the JWT manager instance."""
        self._jwt_manager = jwt_manager
        custom_log("JWT manager set in WebSocketManager")

    def set_room_access_check(self, access_check_func):
        """Set the room access check function."""
        self._room_access_check = access_check_func
        custom_log("Room access check function set")

    def check_room_access(self, room_id: str, user_id: str, user_roles: Set[str]) -> bool:
        """Check if a user has access to a room using the module's access check function."""
        if not self._room_access_check:
            custom_log("No room access check function set")
            return False
        return self._room_access_check(room_id, user_id, user_roles)

    def requires_auth(self, handler: Callable) -> Callable:
        """Decorator to require authentication for WebSocket handlers."""
        @wraps(handler)
        def wrapper(data=None):
            try:
                session_id = request.sid
                
                # Get session data
                session_data = self.get_session_data(session_id)
                if not session_data or 'user_id' not in session_data:
                    custom_log(f"Session {session_id} not authenticated")
                    return {'status': 'error', 'message': 'Authentication required'}
                
                # Update session activity
                self.update_session_activity(session_id)
                
                # Call the handler with session data
                return handler(data, session_data)
            except Exception as e:
                custom_log(f"Error in authenticated handler: {str(e)}")
                return {'status': 'error', 'message': str(e)}
        return wrapper

    def register_handler(self, event: str, handler: Callable):
        """Register a WebSocket event handler without authentication."""
        @self.socketio.on(event)
        def wrapped_handler(data=None):
            try:
                # Skip validation for special events
                if event in ['connect', 'disconnect']:
                    return handler(data)
                    
                # Ensure data is a dictionary if None is provided
                if data is None:
                    data = {}
                    
                # Validate event payload
                error = self.validator.validate_event_payload(event, data)
                if error:
                    custom_log(f"Validation error in {event} handler: {error}")
                    return {'status': 'error', 'message': error}
                    
                # Validate message size based on event type
                if event == 'message':
                    error = self.validator.validate_message(data)
                elif event == 'binary':
                    error = self.validator.validate_binary_data(data)
                else:
                    error = self.validator.validate_json_data(data)
                    
                if error:
                    custom_log(f"Message size validation error in {event} handler: {error}")
                    return {'status': 'error', 'message': error}
                    
                return handler(data)
            except Exception as e:
                custom_log(f"Error in {event} handler: {str(e)}")
                return {'status': 'error', 'message': str(e)}

    def register_authenticated_handler(self, event: str, handler: Callable):
        """Register a WebSocket event handler with authentication."""
        @self.socketio.on(event)
        def wrapped_handler(data=None):
            try:
                # Skip validation for special events
                if event in ['connect', 'disconnect']:
                    return handler(data)
                    
                # Ensure data is a dictionary if None is provided
                if data is None:
                    data = {}
                    
                # Validate event payload
                error = self.validator.validate_event_payload(event, data)
                if error:
                    custom_log(f"Validation error in {event} handler: {error}")
                    return {'status': 'error', 'message': error}
                    
                # Validate message size based on event type
                if event == 'message':
                    error = self.validator.validate_message(data)
                elif event == 'binary':
                    error = self.validator.validate_binary_data(data)
                else:
                    error = self.validator.validate_json_data(data)
                    
                if error:
                    custom_log(f"Message size validation error in {event} handler: {error}")
                    return {'status': 'error', 'message': error}
                    
                return handler(data)
            except Exception as e:
                custom_log(f"Error in {event} handler: {str(e)}")
                return {'status': 'error', 'message': str(e)}

    def create_room(self, room_id: str):
        """Create a new room if it doesn't exist."""
        # Validate room ID
        error = self.validator.validate_room_id(room_id)
        if error:
            custom_log(f"Invalid room ID: {error}")
            return False
            
        if room_id not in self.rooms:
            self.rooms[room_id] = set()
            custom_log(f"Created new room: {room_id}")
            return True
        return False

    def get_room_size(self, room_id: str) -> int:
        """Get the current number of users in a room."""
        return self.redis_manager.get_room_size(room_id)

    def update_room_size(self, room_id: str, delta: int):
        """Update the room size in Redis."""
        self.redis_manager.update_room_size(room_id, delta)

    def check_room_size_limit(self, room_id: str) -> bool:
        """Check if a room has reached its size limit."""
        current_size = self.get_room_size(room_id)
        return current_size >= self._room_size_limit

    def join_room(self, room_id: str, session_id: str, user_id: str = None, user_roles: Set[str] = None):
        """Join a room with access control and size limit check."""
        # Validate room ID
        error = self.validator.validate_room_id(room_id)
        if error:
            custom_log(f"Invalid room ID: {error}")
            return False
            
        # Check room access
        if not self.check_room_access(room_id, user_id, user_roles):
            custom_log(f"Access denied to room {room_id} for user {user_id}")
            return False
            
        # Check room size limit
        if self.check_room_size_limit(room_id):
            custom_log(f"Room {room_id} has reached its size limit")
            return False
            
        # Join the room
        join_room(room_id, sid=session_id)
        
        # Update room tracking
        if room_id not in self.rooms:
            self.rooms[room_id] = set()
        self.rooms[room_id].add(session_id)
        
        if session_id not in self.session_rooms:
            self.session_rooms[session_id] = set()
        self.session_rooms[session_id].add(room_id)
        
        # Update room size in Redis
        self.update_room_size(room_id, 1)
        
        custom_log(f"Session {session_id} joined room {room_id}")
        return True

    def leave_room(self, room_id: str, session_id: str):
        """Leave a room and update room size."""
        # Leave the room
        leave_room(room_id, sid=session_id)
        
        # Update room tracking
        if room_id in self.rooms:
            self.rooms[room_id].discard(session_id)
            if not self.rooms[room_id]:
                del self.rooms[room_id]
                
        if session_id in self.session_rooms:
            self.session_rooms[session_id].discard(room_id)
            if not self.session_rooms[session_id]:
                del self.session_rooms[session_id]
                
        # Update room size in Redis
        self.update_room_size(room_id, -1)
        
        custom_log(f"Session {session_id} left room {room_id}")
        return True

    def broadcast_to_room(self, room_id: str, event: str, data: Dict[str, Any]):
        """Broadcast an event to all users in a room."""
        # Validate room ID
        error = self.validator.validate_room_id(room_id)
        if error:
            custom_log(f"Invalid room ID: {error}")
            return False
            
        # Validate event payload
        error = self.validator.validate_event_payload(event, data)
        if error:
            custom_log(f"Validation error in broadcast: {error}")
            return False
            
        emit(event, data, room=room_id)
        return True

    def broadcast_to_all(self, event: str, data: Dict[str, Any]):
        """Broadcast an event to all connected clients."""
        # Validate event payload
        error = self.validator.validate_event_payload(event, data)
        if error:
            custom_log(f"Validation error in broadcast: {error}")
            return False
            
        emit(event, data)
        return True

    def send_to_session(self, session_id: str, event: str, data: Any):
        """Send message to a specific client."""
        emit(event, data, room=session_id)

    def get_room_members(self, room_id: str) -> set:
        """Get all session IDs in a room."""
        return self.rooms.get(room_id, set())

    def get_rooms_for_session(self, session_id: str) -> set:
        """Get all rooms a session is in."""
        return self.session_rooms.get(session_id, set())

    def cleanup_session(self, session_id: str):
        """Clean up all room memberships for a session."""
        # Remove from all rooms
        if session_id in self.session_rooms:
            for room_id in self.session_rooms[session_id]:
                if room_id in self.rooms:
                    self.rooms[room_id].discard(session_id)
                    # Update room size in Redis
                    self.update_room_size(room_id, -1)
            del self.session_rooms[session_id]
            
        custom_log(f"Cleaned up session {session_id}")

    def run(self, app, **kwargs):
        """Run the WebSocket server."""
        self.socketio.run(app, **kwargs)