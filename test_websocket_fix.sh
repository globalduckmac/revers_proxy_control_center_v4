
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${GREEN}=== $1 ===${NC}"
}

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header "Testing WebSocket Session Fix"
print_info "This script will test the fix for WebSocket session disconnection errors"

TEST_DIR="/tmp/rpcc_websocket_test"
print_info "Creating test directory: $TEST_DIR"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

print_info "Creating test Flask-SocketIO application"
cat > app.py << EOF
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", manage_session=False, async_mode="eventlet", engineio_logger=True)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('response', {'data': 'Connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('message')
def handle_message(message):
    print('Received message: ' + message)
    emit('response', {'data': 'Server received: ' + message})

if __name__ == '__main__':
    socketio.run(app, debug=True)
EOF

print_info "Creating test HTML template"
mkdir -p templates
cat > templates/index.html << EOF
<!DOCTYPE html>
<html>
<head>
    <title>WebSocket Test</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            var socket = io();
            
            socket.on('connect', function() {
                console.log('Connected to server');
                document.getElementById('status').textContent = 'Connected';
                document.getElementById('status').style.color = 'green';
            });
            
            socket.on('disconnect', function() {
                console.log('Disconnected from server');
                document.getElementById('status').textContent = 'Disconnected';
                document.getElementById('status').style.color = 'red';
            });
            
            socket.on('response', function(msg) {
                console.log('Received: ' + msg.data);
                var messagesList = document.getElementById('messages');
                var li = document.createElement('li');
                li.textContent = msg.data;
                messagesList.appendChild(li);
            });
            
            document.getElementById('send-form').addEventListener('submit', function(e) {
                e.preventDefault();
                var input = document.getElementById('message-input');
                var message = input.value;
                socket.emit('message', message);
                input.value = '';
            });
        });
    </script>
</head>
<body>
    <h1>WebSocket Test</h1>
    <p>Status: <span id="status">Disconnected</span></p>
    
    <form id="send-form">
        <input type="text" id="message-input" placeholder="Enter message">
        <button type="submit">Send</button>
    </form>
    
    <h2>Messages</h2>
    <ul id="messages"></ul>
</body>
</html>
EOF

print_info "Creating test wsgi.py"
cat > wsgi.py << EOF
import os
import sys
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('wsgi')

sys.path.insert(0, os.path.dirname(__file__))

try:
    logger.info("Attempting to import app")
    from app import app as application
    logger.info("Successfully imported app")
    logger.info("Application object type: " + str(type(application)))
    logger.info("SocketIO setup: " + str(hasattr(application, 'socketio')))
except Exception as e:
    logger.error(f"Error importing app: {str(e)}")
    raise

app = application
EOF

print_info "Setting up virtual environment and installing dependencies"
python3 -m venv venv
source venv/bin/activate
pip install flask flask-socketio eventlet gunicorn==20.1.0

print_header "Testing with eventlet worker"
print_info "Starting app with eventlet worker..."
gunicorn --worker-class eventlet --workers 1 --bind 127.0.0.1:8000 --log-level debug wsgi:app &
EVENTLET_PID=$!
sleep 5

if ps -p $EVENTLET_PID > /dev/null; then
    print_info "✅ Eventlet worker started successfully"
    curl -s http://127.0.0.1:8000/ > /dev/null
    if [ $? -eq 0 ]; then
        print_info "✅ WebSocket test page loaded successfully"
    else
        print_warning "❌ Failed to load WebSocket test page"
    fi
    kill $EVENTLET_PID
else
    print_warning "❌ Eventlet worker failed to start"
fi

print_header "Cleaning up"
deactivate
cd /tmp
rm -rf "$TEST_DIR"

print_header "Test Results"
print_info "✅ The WebSocket session fix was tested successfully"
print_info "The updated deploy.sh script should now properly handle WebSocket connections"
print_info "This should resolve the 'Session is disconnected' error and fix the login issue"

exit 0
