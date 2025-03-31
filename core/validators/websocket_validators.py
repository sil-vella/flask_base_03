from typing import Dict, Any, Optional, Set
from tools.logger.custom_logging import custom_log
import re
from datetime import datetime

class WebSocketValidator:
    """Validates WebSocket inputs and sanitizes data."""
    
    # Constants for validation
    MAX_MESSAGE_LENGTH = 1000
    MAX_ROOM_ID_LENGTH = 50
    MAX_USERNAME_LENGTH = 50
    ALLOWED_ROOM_ID_CHARS = re.compile(r'^[a-zA-Z0-9_-]+$')
    ALLOWED_USERNAME_CHARS = re.compile(r'^[a-zA-Z0-9_-]+$')
    
    @staticmethod
    def validate_message(data: Dict[str, Any]) -> Optional[str]:
        """Validate message content."""
        if not isinstance(data, dict):
            return "Message data must be a dictionary"
            
        message = data.get('message')
        if not message:
            return "Message content is required"
            
        if not isinstance(message, str):
            return "Message must be a string"
            
        if len(message) > WebSocketValidator.MAX_MESSAGE_LENGTH:
            return f"Message too long (max {WebSocketValidator.MAX_MESSAGE_LENGTH} characters)"
            
        return None
        
    @staticmethod
    def validate_room_id(room_id: str) -> Optional[str]:
        """Validate room ID."""
        if not room_id:
            return "Room ID is required"
            
        if not isinstance(room_id, str):
            return "Room ID must be a string"
            
        if len(room_id) > WebSocketValidator.MAX_ROOM_ID_LENGTH:
            return f"Room ID too long (max {WebSocketValidator.MAX_ROOM_ID_LENGTH} characters)"
            
        if not WebSocketValidator.ALLOWED_ROOM_ID_CHARS.match(room_id):
            return "Room ID contains invalid characters"
            
        return None
        
    @staticmethod
    def validate_user_data(user_data: Dict[str, Any]) -> Optional[str]:
        """Validate user data."""
        if not isinstance(user_data, dict):
            return "User data must be a dictionary"
            
        required_fields = {'id', 'username', 'email'}
        missing_fields = required_fields - set(user_data.keys())
        if missing_fields:
            return f"Missing required fields: {', '.join(missing_fields)}"
            
        # Validate username
        username = user_data.get('username')
        if not isinstance(username, str):
            return "Username must be a string"
            
        if len(username) > WebSocketValidator.MAX_USERNAME_LENGTH:
            return f"Username too long (max {WebSocketValidator.MAX_USERNAME_LENGTH} characters)"
            
        if not WebSocketValidator.ALLOWED_USERNAME_CHARS.match(username):
            return "Username contains invalid characters"
            
        # Validate email
        email = user_data.get('email')
        if not isinstance(email, str):
            return "Email must be a string"
            
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return "Invalid email format"
            
        # Validate user ID
        user_id = user_data.get('id')
        if not isinstance(user_id, (int, str)):
            return "User ID must be an integer or string"
            
        if isinstance(user_id, str) and not user_id.isdigit():
            return "User ID must be a valid number"
            
        return None
        
    @staticmethod
    def validate_event_payload(event: str, data: Dict[str, Any]) -> Optional[str]:
        """Validate event-specific payload."""
        validators = {
            'message': WebSocketValidator.validate_message,
            'join': lambda d: WebSocketValidator.validate_room_id(d.get('room_id')),
            'leave': lambda d: WebSocketValidator.validate_room_id(d.get('room_id')),
            'button_press': lambda d: None,  # No validation needed
            'get_counter': lambda d: None,   # No validation needed
            'get_users': lambda d: None      # No validation needed
        }
        
        validator = validators.get(event)
        if validator:
            return validator(data)
            
        return None
        
    @staticmethod
    def sanitize_message(message: str) -> str:
        """Sanitize message content."""
        # Remove HTML tags
        message = re.sub(r'<[^>]+>', '', message)
        
        # Remove script tags and their content
        message = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', message)
        
        # Remove potentially dangerous attributes
        message = re.sub(r'on\w+="[^"]*"', '', message)
        
        return message.strip()
        
    @staticmethod
    def sanitize_user_data(user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize user data."""
        sanitized = user_data.copy()
        
        # Sanitize username
        if 'username' in sanitized:
            sanitized['username'] = re.sub(r'[^a-zA-Z0-9_-]', '', sanitized['username'])
            
        # Sanitize email
        if 'email' in sanitized:
            sanitized['email'] = sanitized['email'].lower().strip()
            
        return sanitized 