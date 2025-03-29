import unittest
from unittest.mock import MagicMock, patch
from plugins.main_plugin.modules.websocket_module.websocket_module import WebSocketModule
from core.managers.websocket_manager import WebSocketManager
from flask import Flask
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestWebSocketModule(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test."""
        self.app = Flask(__name__)
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.request_context = self.app.test_request_context()
        self.request_context.push()
        
        # Create a mock request object with sid
        self.mock_request = MagicMock()
        self.mock_request.sid = 'test_session_id'
        
        # Start patching request at the module level
        self.request_patcher = patch('plugins.main_plugin.modules.websocket_module.websocket_module.request', self.mock_request)
        self.request_patcher.start()
        
        self.websocket_manager = MagicMock(spec=WebSocketManager)
        self.websocket_module = WebSocketModule(self.websocket_manager)

    def tearDown(self):
        """Clean up after each test."""
        self.request_patcher.stop()
        self.request_context.pop()
        self.app_context.pop()

    def test_handle_connect(self):
        """Test handling of new connections."""
        result = self.websocket_module._handle_connect()
        
        self.assertEqual(result, {
            'status': 'connected',
            'session_id': 'test_session_id'
        })

    def test_handle_disconnect(self):
        """Test handling of disconnections."""
        self.websocket_module._handle_disconnect()
        self.websocket_manager.cleanup_session.assert_called_once_with('test_session_id')

    def test_handle_join(self):
        """Test handling of joining a room."""
        data = {'room_id': 'test_room'}
        
        result = self.websocket_module._handle_join(data)
        
        self.assertEqual(result, {
            'status': 'joined',
            'room_id': 'test_room'
        })
        self.websocket_manager.join_room.assert_called_once_with('test_room', 'test_session_id')

    def test_handle_join_missing_room_id(self):
        """Test handling of joining a room with missing room_id."""
        data = {}
        
        with self.assertRaises(ValueError):
            self.websocket_module._handle_join(data)

    def test_handle_leave(self):
        """Test handling of leaving a room."""
        data = {'room_id': 'test_room'}
        
        result = self.websocket_module._handle_leave(data)
        
        self.assertEqual(result, {
            'status': 'left',
            'room_id': 'test_room'
        })
        self.websocket_manager.leave_room.assert_called_once_with('test_room', 'test_session_id')

    def test_handle_leave_missing_room_id(self):
        """Test handling of leaving a room with missing room_id."""
        data = {}
        
        with self.assertRaises(ValueError):
            self.websocket_module._handle_leave(data)

    def test_handle_message(self):
        """Test handling of messages."""
        data = {
            'room_id': 'test_room',
            'message': 'test message'
        }
        
        result = self.websocket_module._handle_message(data)
        
        self.assertEqual(result, {'status': 'sent'})
        self.websocket_manager.broadcast_to_room.assert_called_once_with(
            'test_room',
            'message',
            {
                'session_id': 'test_session_id',
                'message': 'test message'
            }
        )

    def test_handle_message_no_room(self):
        """Test handling of messages without a room."""
        data = {'message': 'test message'}
        
        result = self.websocket_module._handle_message(data)
        
        self.assertEqual(result, {'status': 'sent'})
        self.websocket_manager.send_to_session.assert_called_once_with(
            'test_session_id',
            'message',
            {
                'session_id': 'test_session_id',
                'message': 'test message'
            }
        )

    def test_handle_message_missing_message(self):
        """Test handling of messages with missing message content."""
        data = {'room_id': 'test_room'}
        
        with self.assertRaises(ValueError):
            self.websocket_module._handle_message(data)

    def test_broadcast_to_room(self):
        """Test broadcasting to a room."""
        self.websocket_module.broadcast_to_room('test_room', 'test_event', {'data': 'test'})
        self.websocket_manager.broadcast_to_room.assert_called_once_with('test_room', 'test_event', {'data': 'test'})

    def test_send_to_session(self):
        """Test sending to a specific session."""
        self.websocket_module.send_to_session('test_session', 'test_event', {'data': 'test'})
        self.websocket_manager.send_to_session.assert_called_once_with('test_session', 'test_event', {'data': 'test'})

    def test_get_room_members(self):
        """Test getting room members."""
        self.websocket_module.get_room_members('test_room')
        self.websocket_manager.get_room_members.assert_called_once_with('test_room')

    def test_get_rooms_for_session(self):
        """Test getting rooms for a session."""
        self.websocket_module.get_rooms_for_session('test_session')
        self.websocket_manager.get_rooms_for_session.assert_called_once_with('test_session')

if __name__ == '__main__':
    unittest.main() 