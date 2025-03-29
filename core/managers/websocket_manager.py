from flask_socketio import SocketIO, emit, join_room, leave_room
from typing import Dict, Any, Callable
from tools.logger.custom_logging import custom_log
import functools

class WebSocketManager:
    def __init__(self):
        self.socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')
        self.rooms: Dict[str, set] = {}  # room_id -> set of session_ids
        self.handlers: Dict[str, Callable] = {}  # event_name -> handler function
        custom_log("WebSocketManager initialized")

    def initialize(self, app):
        """Initialize WebSocket support with the Flask app."""
        self.socketio.init_app(app)
        
        # Register basic connection handlers for root namespace
        @self.socketio.on('connect', namespace='/')
        def handle_connect():
            custom_log("Client connected")
            emit('connection_response', {'data': 'Connected'}, namespace='/')

        @self.socketio.on('disconnect', namespace='/')
        def handle_disconnect():
            custom_log("Client disconnected")

        @self.socketio.on('join', namespace='/')
        def handle_join(data):
            room = data.get('room')
            if room:
                join_room(room)
                custom_log(f"Client joined room: {room}")
                emit('join_response', {'data': f'Joined room {room}'}, namespace='/')

        @self.socketio.on('leave', namespace='/')
        def handle_leave(data):
            room = data.get('room')
            if room:
                leave_room(room)
                custom_log(f"Client left room: {room}")
                emit('leave_response', {'data': f'Left room {room}'}, namespace='/')

        custom_log("WebSocket support initialized with Flask app")

    def register_handler(self, event: str, namespace='/'):
        """Decorator to register WebSocket event handlers."""
        def decorator(f):
            @functools.wraps(f)
            def wrapped(*args, **kwargs):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    custom_log(f"Error in WebSocket handler {event}: {str(e)}")
                    emit('error', {'message': str(e)}, namespace=namespace)
            
            # Register the handler with SocketIO
            self.socketio.on(event, namespace=namespace)(wrapped)
            self.handlers[f"{namespace}:{event}"] = wrapped
            return wrapped
        return decorator

    def create_room(self, room_id: str):
        """Create a new WebSocket room."""
        if room_id not in self.rooms:
            self.rooms[room_id] = set()
            custom_log(f"Created WebSocket room: {room_id}")

    def join_room(self, room_id: str, session_id: str):
        """Join a WebSocket room."""
        if room_id not in self.rooms:
            self.create_room(room_id)
        self.rooms[room_id].add(session_id)
        join_room(room_id)
        custom_log(f"Session {session_id} joined room {room_id}")

    def leave_room(self, room_id: str, session_id: str):
        """Leave a WebSocket room."""
        if room_id in self.rooms and session_id in self.rooms[room_id]:
            self.rooms[room_id].remove(session_id)
            leave_room(room_id)
            custom_log(f"Session {session_id} left room {room_id}")

    def broadcast_to_room(self, room_id: str, event: str, data: Any, namespace='/'):
        """Broadcast a message to all clients in a room."""
        if room_id in self.rooms:
            emit(event, data, room=room_id, namespace=namespace)
            custom_log(f"Broadcast {event} to room {room_id}")

    def send_to_session(self, session_id: str, event: str, data: Any, namespace='/'):
        """Send a message to a specific client."""
        emit(event, data, room=session_id, namespace=namespace)
        custom_log(f"Sent {event} to session {session_id}")

    def get_room_members(self, room_id: str) -> set:
        """Get all session IDs in a room."""
        return self.rooms.get(room_id, set())

    def get_rooms_for_session(self, session_id: str) -> set:
        """Get all rooms a session is in."""
        return {room_id for room_id, sessions in self.rooms.items() 
                if session_id in sessions}

    def cleanup_session(self, session_id: str):
        """Clean up all rooms for a session."""
        for room_id in self.get_rooms_for_session(session_id):
            self.leave_room(room_id, session_id)
        custom_log(f"Cleaned up all rooms for session {session_id}")

    def run(self, app, **kwargs):
        """Run the WebSocket server."""
        self.socketio.run(app, **kwargs) 