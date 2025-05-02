#!/bin/bash

echo "=== Testing Worker Compatibility Fix ==="
echo "[INFO] This script will test compatible worker configurations for Flask-SocketIO"

# Create test directory
TEST_DIR="/tmp/rpcc_worker_test"
echo "[INFO] Creating test directory: $TEST_DIR"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# Set up Python environment
echo "[INFO] Setting up Python environment"
python3 -m venv venv
source venv/bin/activate

echo "[INFO] Installing required packages"
pip install Flask==2.3.3 Flask-SocketIO==5.3.4 gunicorn==21.2.0 gevent==23.9.1 gevent-websocket==0.10.1

# Create test app
echo "[INFO] Creating test Flask-SocketIO application"
cat > app.py << 'APPEOF'
from flask import Flask
from flask_socketio import SocketIO
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-secret'

# Use gevent as async mode
socketio = SocketIO(app, async_mode='gevent', manage_session=False, logger=True, engineio_logger=True)

@app.route('/')
def index():
    return "WebSocket Test (gevent)"

@socketio.on('connect')
def handle_connect():
    logger.info("Client connected")
    return {"status": "connected"}

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected")

if __name__ == '__main__':
    socketio.run(app, debug=True)
APPEOF

# Create WSGI entry point
echo "[INFO] Creating WSGI entry point"
cat > wsgi.py << 'WSGIEOF'
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('wsgi')

try:
    from app import app, socketio
    logger.info("Successfully imported app and socketio")
except Exception as e:
    logger.error(f"Error importing app: {str(e)}")
    raise

application = app
WSGIEOF

# Test gevent worker
echo "=== Testing with gevent worker ==="
echo "[INFO] Starting app with gevent worker..."

# Use a random port to avoid conflicts
PORT=$((8100 + RANDOM % 1000))
echo "[INFO] Using port: $PORT"

# Start gunicorn with gevent worker
gunicorn --worker-class gevent --workers 1 --bind "127.0.0.1:$PORT" --log-level debug wsgi:application &
GEVENT_PID=$!
sleep 5

# Check if process is running
if ps -p $GEVENT_PID > /dev/null; then
    echo "[SUCCESS] ✅ gevent worker started successfully"
    
    # Test if app is accessible
    RESPONSE=$(curl -s "http://127.0.0.1:$PORT/" || echo "Failed to connect")
    if [[ $RESPONSE == *"WebSocket Test"* ]]; then
        echo "[SUCCESS] ✅ App is accessible with gevent worker"
    else
        echo "[WARNING] ❌ App is not accessible with gevent worker"
    fi
    
    # Kill the process
    kill $GEVENT_PID
    sleep 2
else
    echo "[ERROR] ❌ gevent worker failed to start"
fi

# Clean up
echo "=== Cleaning up ==="
deactivate
cd /tmp
rm -rf "$TEST_DIR"

echo "=== Test Results ==="
echo "[INFO] The worker compatibility test was completed"
echo "[INFO] Based on the test results, update deploy.sh to use a compatible worker configuration"

exit 0
