import socketio
import time
from tools.logger.custom_logging import custom_log

# Create a Socket.IO client
sio = socketio.Client()

@sio.event(namespace='/')
def connect():
    custom_log("Connected to WebSocket server")

@sio.event(namespace='/')
def disconnect():
    custom_log("Disconnected from WebSocket server")

@sio.event(namespace='/')
def connection_response(data):
    custom_log(f"Received connection response: {data}")
    if data.get('data') == 'Connected':
        custom_log("Successfully connected to WebSocket server")
        # Test join/leave operations
        test_room = "test_room"
        sio.emit('join', {'room': test_room}, namespace='/')

@sio.event(namespace='/')
def join_response(data):
    custom_log(f"Received join response: {data}")
    if 'data' in data:
        # After successful join, test leaving the room
        test_room = "test_room"
        sio.emit('leave', {'room': test_room}, namespace='/')

@sio.event(namespace='/')
def leave_response(data):
    custom_log(f"Received leave response: {data}")
    if 'data' in data:
        # After successful leave, disconnect
        sio.disconnect()

@sio.event(namespace='/')
def error(data):
    custom_log(f"Received error: {data}")

def main():
    try:
        # Connect to the WebSocket server with namespace
        custom_log("Attempting to connect to WebSocket server...")
        sio.connect('http://localhost:5000', namespaces=['/'])
        
        # Wait for events to complete
        time.sleep(5)
        
    except Exception as e:
        custom_log(f"Failed to connect to WebSocket server: {str(e)}")
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    main() 