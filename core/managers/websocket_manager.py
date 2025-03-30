from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request
from typing import Dict, Any, Set, Callable, Optional
from tools.logger.custom_logging import custom_log
from core.managers.redis_manager import RedisManager
from utils.config.config import Config
import time
from datetime import datetime

class WebSocketManager:
    def __init__(self):
        self.redis_manager = RedisManager()
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

    def store_session_data(self, session_id: str, client_id: str, origin: str):
        """Store session information in Redis."""
        session_data = {
            'client_id': client_id,
            'origin': origin,
            'connected_at': datetime.utcnow().isoformat(),
            'last_active': datetime.utcnow().isoformat()
        }
        self.redis_manager.set(f"ws:session:{session_id}", session_data, expire=Config.WS_SESSION_TTL)

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

    def register_handler(self, event: str, handler: Callable):
        """Register a WebSocket event handler."""
        @self.socketio.on(event)
        def wrapped_handler(data=None):
            try:
                custom_log(f"Received {event} event with data: {data}")
                result = handler(data)
                custom_log(f"Handler result for {event}: {result}")
                return result
            except Exception as e:
                custom_log(f"Error in WebSocket handler {event}: {str(e)}")
                emit('error', {'message': str(e)})
        custom_log(f"Registered handler for event: {event}")

    def create_room(self, room_id: str):
        """Create a new WebSocket room."""
        if room_id not in self.rooms:
            self.rooms[room_id] = set()
            custom_log(f"Created WebSocket room: {room_id}")

    def join_room(self, room_id: str, session_id: str):
        """Add a session to a room."""
        if room_id not in self.rooms:
            self.rooms[room_id] = set()
        self.rooms[room_id].add(session_id)
        
        if session_id not in self.session_rooms:
            self.session_rooms[session_id] = set()
        self.session_rooms[session_id].add(room_id)
        
        join_room(room_id)
        custom_log(f"Session {session_id} joined room {room_id}")

    def leave_room(self, room_id: str, session_id: str):
        """Remove a session from a room."""
        if room_id in self.rooms:
            self.rooms[room_id].discard(session_id)
            if not self.rooms[room_id]:
                del self.rooms[room_id]
        
        if session_id in self.session_rooms:
            self.session_rooms[session_id].discard(room_id)
            if not self.session_rooms[session_id]:
                del self.session_rooms[session_id]
        
        leave_room(room_id)
        custom_log(f"Session {session_id} left room {room_id}")

    def broadcast_to_room(self, room_id: str, event: str, data: Any):
        """Broadcast a message to all clients in a room."""
        if room_id in self.rooms:
            emit(event, data, room=room_id, broadcast=True)
            custom_log(f"Broadcast {event} to room {room_id}")

    def send_to_session(self, session_id: str, event: str, data: Any):
        """Send a message to a specific client."""
        emit(event, data, room=session_id)
        custom_log(f"Sent {event} to session {session_id}")

    def get_room_members(self, room_id: str) -> set:
        """Get all session IDs in a room."""
        return self.rooms.get(room_id, set())

    def get_rooms_for_session(self, session_id: str) -> set:
        """Get all rooms a session is in."""
        return self.session_rooms.get(session_id, set())

    def cleanup_session(self, session_id: str):
        """Clean up all room memberships for a session."""
        if session_id in self.session_rooms:
            for room_id in self.session_rooms[session_id]:
                if room_id in self.rooms:
                    self.rooms[room_id].discard(session_id)
                    if not self.rooms[room_id]:
                        del self.rooms[room_id]
            del self.session_rooms[session_id]
            custom_log(f"Cleaned up session {session_id}")

    def run(self, app, **kwargs):
        """Run the WebSocket server."""
        self.socketio.run(app, **kwargs)