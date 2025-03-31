from typing import Dict, Any, Optional, Set
from tools.logger.custom_logging import custom_log
import re
from datetime import datetime
import json
from utils.config.config import Config

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
            return "Message content must be a string"
            
        # Check message length
        if len(message) > Config.WS_MAX_MESSAGE_LENGTH:
            return f"Message exceeds maximum length of {Config.WS_MAX_MESSAGE_LENGTH} characters"
            
        # Sanitize message content
        data['message'] = WebSocketValidator.sanitize_message(message)
        return None

    @staticmethod
    def validate_binary_data(data: bytes) -> Optional[str]:
        """Validate binary data size."""
        if not isinstance(data, bytes):
            return "Data must be binary"
            
        if len(data) > Config.WS_MAX_BINARY_SIZE:
            return f"Binary data exceeds maximum size of {Config.WS_MAX_BINARY_SIZE} bytes"
            
        return None

    @staticmethod
    def validate_json_data(data: Dict[str, Any]) -> Optional[str]:
        """Validate JSON data structure and size."""
        if not isinstance(data, dict):
            return "Data must be a JSON object"
            
        # Check JSON size
        json_str = json.dumps(data)
        if len(json_str) > Config.WS_MAX_JSON_SIZE:
            return f"JSON data exceeds maximum size of {Config.WS_MAX_JSON_SIZE} bytes"
            
        # Check nesting depth
        depth = WebSocketValidator._get_json_depth(data)
        if depth > Config.WS_MAX_JSON_DEPTH:
            return f"JSON data exceeds maximum nesting depth of {Config.WS_MAX_JSON_DEPTH}"
            
        # Check array size
        if WebSocketValidator._get_max_array_size(data) > Config.WS_MAX_ARRAY_SIZE:
            return f"JSON array exceeds maximum size of {Config.WS_MAX_ARRAY_SIZE} elements"
            
        # Check object size
        if WebSocketValidator._get_max_object_size(data) > Config.WS_MAX_OBJECT_SIZE:
            return f"JSON object exceeds maximum size of {Config.WS_MAX_OBJECT_SIZE} properties"
            
        return None

    @staticmethod
    def _get_json_depth(obj: Any, current_depth: int = 0) -> int:
        """Calculate the maximum nesting depth of a JSON structure."""
        if not isinstance(obj, (dict, list)):
            return current_depth
            
        max_depth = current_depth + 1
        if isinstance(obj, dict):
            for value in obj.values():
                max_depth = max(max_depth, WebSocketValidator._get_json_depth(value, current_depth + 1))
        else:  # list
            for item in obj:
                max_depth = max(max_depth, WebSocketValidator._get_json_depth(item, current_depth + 1))
        return max_depth

    @staticmethod
    def _get_max_array_size(obj: Any) -> int:
        """Calculate the maximum size of any array in the JSON structure."""
        if not isinstance(obj, (dict, list)):
            return 0
            
        max_size = len(obj) if isinstance(obj, list) else 0
        if isinstance(obj, dict):
            for value in obj.values():
                max_size = max(max_size, WebSocketValidator._get_max_array_size(value))
        else:  # list
            for item in obj:
                max_size = max(max_size, WebSocketValidator._get_max_array_size(item))
        return max_size

    @staticmethod
    def _get_max_object_size(obj: Any) -> int:
        """Calculate the maximum number of properties in any object in the JSON structure."""
        if not isinstance(obj, (dict, list)):
            return 0
            
        max_size = len(obj) if isinstance(obj, dict) else 0
        if isinstance(obj, dict):
            for value in obj.values():
                max_size = max(max_size, WebSocketValidator._get_max_object_size(value))
        else:  # list
            for item in obj:
                max_size = max(max_size, WebSocketValidator._get_max_object_size(item))
        return max_size

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