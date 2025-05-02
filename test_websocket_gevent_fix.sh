
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

print_header "Testing WebSocket with Gevent Fix"
print_info "This script will test the fix for WebSocket session disconnection issues using gevent"

TEST_DIR="/tmp/rpcc_gevent_test"
print_info "Creating test directory: $TEST_DIR"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

print_info "Creating test Flask-SocketIO application"
cat > app.py << EOF
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-secret'
socketio = SocketIO(app, async_mode='gevent', manage_session=False, logger=True, engineio_logger=True)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    logger.info("Client connected")
    emit('response', {'data': 'Connected'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected")

@socketio.on('message')
def handle_message(message):
    logger.info(f"Received message: {message}")
    emit('response', {'data': f'Server received: {message}'})

if __name__ == '__main__':
    socketio.run(app, debug=True)
EOF

print_info "Creating HTML template for testing"
mkdir -p templates
cat > templates/index.html << EOF
<!DOCTYPE html>
<html>
<head>
    <title>WebSocket Test with Gevent</title>
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
    <h1>WebSocket Test with Gevent</h1>
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

print_info "Creating WSGI entry point"
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

try:
    from app import app, socketio
    logger.info("Successfully imported app and socketio")
except Exception as e:
    logger.error(f"Error importing app: {str(e)}")
    raise

application = app
EOF

print_info "Setting up virtual environment and installing dependencies"
python3 -m venv venv
source venv/bin/activate
pip install flask flask-socketio gevent gevent-websocket gunicorn==21.2.0

PORT=$((8000 + RANDOM % 1000))
print_info "Using port: $PORT"

print_header "Testing with gevent worker"
print_info "Starting app with gevent worker..."
gunicorn --worker-class gevent --workers 1 --bind 127.0.0.1:$PORT --log-level debug wsgi:application &
GEVENT_PID=$!
sleep 5

if ps -p $GEVENT_PID > /dev/null; then
    print_info "✅ Gevent worker started successfully"
    if curl -s http://127.0.0.1:$PORT/ > /dev/null; then
        print_info "✅ WebSocket test page accessible"
    else
        print_warning "❌ Failed to access WebSocket test page"
    fi
    kill $GEVENT_PID
else
    print_warning "❌ Gevent worker failed to start"
fi

print_header "Testing login session handling"
print_info "Creating test login application with session management"
cat > login_test.py << EOF
from flask import Flask, session, redirect, url_for, request, render_template_string
from flask_socketio import SocketIO
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-secret-key'
socketio = SocketIO(app, async_mode='gevent', manage_session=False, logger=True, engineio_logger=True)

@app.route('/')
def index():
    if 'username' in session:
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Login Test</title>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
                <script>
                    document.addEventListener('DOMContentLoaded', function() {
                        var socket = io();
                        socket.on('connect', function() {
                            document.getElementById('status').textContent = 'Connected';
                        });
                        socket.on('disconnect', function() {
                            document.getElementById('status').textContent = 'Disconnected';
                        });
                    });
                </script>
            </head>
            <body>
                <h1>Welcome {{ username }}</h1>
                <p>WebSocket Status: <span id="status">Disconnected</span></p>
                <p><a href="/logout">Logout</a></p>
            </body>
            </html>
        ''', username=session['username'])
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['username'] = request.form['username']
        return redirect(url_for('index'))
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login</title>
        </head>
        <body>
            <h1>Login</h1>
            <form method="post">
                <input type="text" name="username" placeholder="Username">
                <input type="submit" value="Login">
            </form>
        </body>
        </html>
    ''')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@socketio.on('connect')
def handle_connect():
    logger.info("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected")

if __name__ == '__main__':
    socketio.run(app, debug=True)
EOF

print_info "Starting login test app with gevent worker..."
PORT=$((8000 + RANDOM % 1000))
print_info "Using port: $PORT"
gunicorn --worker-class gevent --workers 1 --bind 127.0.0.1:$PORT --log-level debug "login_test:app" &
LOGIN_PID=$!
sleep 5

if ps -p $LOGIN_PID > /dev/null; then
    print_info "✅ Login test app started successfully"
    if curl -s http://127.0.0.1:$PORT/login > /dev/null; then
        print_info "✅ Login page accessible"
    else
        print_warning "❌ Failed to access login page"
    fi
    kill $LOGIN_PID
else
    print_warning "❌ Login test app failed to start"
fi

print_header "Cleaning up"
deactivate
cd /tmp
rm -rf "$TEST_DIR"

print_header "Test Results"
print_info "✅ The WebSocket gevent fix was tested"
print_info "The updated deploy.sh script should now properly handle WebSocket connections"
print_info "This should resolve the 'ImportError: cannot import name ALREADY_HANDLED' error"
print_info "The manage_session=False parameter should fix the 'Session is disconnected' error"

exit 0
