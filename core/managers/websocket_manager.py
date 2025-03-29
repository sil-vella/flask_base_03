from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request
from typing import Dict, Any, Set, Callable
from tools.logger.custom_logging import custom_log

class WebSocketManager:
    def __init__(self):
        self.socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')
        self.rooms: Dict[str, Set[str]] = {}  # room_id -> set of session_ids
        self.session_rooms: Dict[str, Set[str]] = {}  # session_id -> set of room_ids
        custom_log("WebSocketManager initialized")

    def initialize(self, app):
        """Initialize WebSocket support with the Flask app."""
        self.socketio.init_app(app)
        custom_log("WebSocket support initialized with Flask app")

    def register_handler(self, event: str, handler: Callable):
        """Register a WebSocket event handler."""
        @self.socketio.on(event)
        def wrapped_handler(*args, **kwargs):
            try:
                return handler(*args, **kwargs)
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
            emit(event, data, room=room_id)
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