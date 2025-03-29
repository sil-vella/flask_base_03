import socketio
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a Socket.IO client
sio = socketio.Client()

# Test room ID
test_room = 'test_room_1'

@sio.event
def connect():
    """Handle connection event."""
    logger.info("Connected to server")
    # Join a room after connection
    sio.emit('join', {'room_id': test_room})  # Removed namespace parameter

@sio.event
def disconnect():
    """Handle disconnection event."""
    logger.info("Disconnected from server")

@sio.event
def connection_response(data):
    """Handle connection response."""
    logger.info(f"Connection response: {data}")

@sio.event
def join_response(data):
    """Handle join room response."""
    logger.info(f"Join response: {data}")
    # Leave the room after 5 seconds
    time.sleep(5)
    sio.emit('leave', {'room_id': test_room})  # Removed namespace parameter

@sio.event
def leave_response(data):
    """Handle leave room response."""
    logger.info(f"Leave response: {data}")
    # Disconnect after leaving
    sio.disconnect()

@sio.event
def message(data):  # Changed from 'error' to 'message' to match server
    """Handle message events."""
    logger.info(f"Message received: {data}")

@sio.event
def error(data):
    """Handle error events."""
    logger.error(f"Error: {data}")

def main():
    """Main function to run the test client."""
    try:
        # Connect to the server (removed namespaces parameter)
        sio.connect('http://localhost:5000')
        
        # Wait for events to be processed
        while sio.connected:
            time.sleep(0.1)
            
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == '__main__':
    main()