from flask import request
from core.managers.websocket_manager import WebSocketManager
from tools.logger.custom_logging import custom_log
from typing import Dict, Any

class WebSocketModule:
    def __init__(self, websocket_manager: WebSocketManager):
        self.websocket_manager = websocket_manager
        self._register_handlers()
        custom_log("WebSocketModule initialized")

    def _register_handlers(self):
        """Register all WebSocket event handlers."""
        self.websocket_manager.register_handler('connect', self._handle_connect)
        self.websocket_manager.register_handler('disconnect', self._handle_disconnect)
        self.websocket_manager.register_handler('join', self._handle_join)
        self.websocket_manager.register_handler('leave', self._handle_leave)
        self.websocket_manager.register_handler('message', self._handle_message)
        custom_log("WebSocket event handlers registered")

    def _handle_connect(self):
        """Handle new WebSocket connections."""
        session_id = request.sid
        custom_log(f"New WebSocket connection: {session_id}")
        return {'status': 'connected', 'session_id': session_id}

    def _handle_disconnect(self):
        """Handle WebSocket disconnections."""
        session_id = request.sid
        self.websocket_manager.cleanup_session(session_id)
        custom_log(f"WebSocket disconnected: {session_id}")

    def _handle_join(self, data: Dict[str, Any]):
        """Handle joining a room."""
        session_id = request.sid
        room_id = data.get('room_id')
        if not room_id:
            raise ValueError("room_id is required")
        
        self.websocket_manager.join_room(room_id, session_id)
        return {'status': 'joined', 'room_id': room_id}

    def _handle_leave(self, data: Dict[str, Any]):
        """Handle leaving a room."""
        session_id = request.sid
        room_id = data.get('room_id')
        if not room_id:
            raise ValueError("room_id is required")
        
        self.websocket_manager.leave_room(room_id, session_id)
        return {'status': 'left', 'room_id': room_id}

    def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming messages."""
        session_id = request.sid
        room_id = data.get('room_id')
        message = data.get('message')
        
        if not message:
            raise ValueError("message is required")
        
        if room_id:
            # Broadcast to room if room_id is provided
            self.websocket_manager.broadcast_to_room(room_id, 'message', {
                'session_id': session_id,
                'message': message
            })
        else:
            # Echo back to sender if no room_id
            self.websocket_manager.send_to_session(session_id, 'message', {
                'session_id': session_id,
                'message': message
            })
        
        return {'status': 'sent'}

    def broadcast_to_room(self, room_id: str, event: str, data: Any):
        """Broadcast a message to all clients in a room."""
        self.websocket_manager.broadcast_to_room(room_id, event, data)

    def send_to_session(self, session_id: str, event: str, data: Any):
        """Send a message to a specific client."""
        self.websocket_manager.send_to_session(session_id, event, data)

    def get_room_members(self, room_id: str) -> set:
        """Get all session IDs in a room."""
        return self.websocket_manager.get_room_members(room_id)

    def get_rooms_for_session(self, session_id: str) -> set:
        """Get all rooms a session is in."""
        return self.websocket_manager.get_rooms_for_session(session_id)