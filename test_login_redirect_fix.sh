
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

print_header "Testing Login Redirect Fix"
print_info "This script will test the fix for login redirect issues in SPA mode"

TEST_DIR="/tmp/rpcc_login_test"
print_info "Creating test directory: $TEST_DIR"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

print_info "Creating test Flask-SocketIO application with login functionality"
cat > app.py << EOF
import logging
from flask import Flask, render_template, redirect, url_for, request, jsonify, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO

logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'test-secret-key'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

socketio = SocketIO(app, cors_allowed_origins="*", manage_session=False, async_mode="gevent", engineio_logger=True)

class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

users = {
    'admin': User(1, 'admin', 'admin')
}

@login_manager.user_loader
def load_user(user_id):
    return User(user_id, 'admin', 'admin') if user_id == '1' else None

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        user = users.get(username)
        
        if not user or user.password != password:
            flash('Invalid username or password', 'danger')
            return render_template('login.html')
        
        login_user(user, remember=remember)
        logger.info(f"User {username} logged in")
        
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('dashboard'))
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.context_processor
def inject_spa_mode():
    """Add SPA mode detection to templates."""
    is_spa_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    return {'is_spa_request': is_spa_request}

@app.after_request
def after_request(response):
    """Handle AJAX requests for SPA."""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if response.status_code in (301, 302, 303, 307, 308):
            app.logger.info(f"Converting redirect response to JSON for AJAX request: {response.location}")
            return jsonify({
                'redirect': response.location
            })
        elif response.content_type == 'text/html; charset=utf-8':
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.data, 'html.parser')
            content = soup.find(id='spa-content')
            if content:
                return jsonify({
                    'title': soup.title.string if soup.title else '',
                    'content': str(content),
                    'url': request.url
                })
    return response

import os
os.makedirs('templates', exist_ok=True)

with open('templates/layout.html', 'w') as f:
    f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>{% block title %}Test App{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <style>
        .alert-container {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
        }
    </style>
</head>
<body>
    <div class="container mt-4">
        <div id="spa-content">
            {% block content %}{% endblock %}
        </div>
    </div>
    
    <script>
        // SPA Forms Handler
        $(document).ready(function() {
            $('form').on('submit', function(e) {
                if ($(this).hasClass('no-spa') || $(this).attr('enctype') === 'multipart/form-data') {
                    return;
                }
                
                if ($(this).attr('method').toLowerCase() === 'post') {
                    e.preventDefault();
                    
                    var form = $(this);
                    var formData = new FormData(this);
                    var submitButton = form.find('button[type="submit"]');
                    
                    if (submitButton.length) {
                        submitButton.prop('disabled', true);
                        submitButton.html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...');
                    }
                    
                    $.ajax({
                        url: form.attr('action'),
                        method: 'POST',
                        data: formData,
                        processData: false,
                        contentType: false,
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest'
                        },
                        success: function(result) {
                            console.log('Form submission result:', result);
                            
                            if (result.redirect) {
                                window.location.href = result.redirect;
                            } else if (result.content) {
                                $('#spa-content').html(result.content);
                            }
                        },
                        error: function(xhr, status, error) {
                            console.error('Form submission error:', error);
                            showMessage('An error occurred while submitting the form.', 'danger');
                        },
                        complete: function() {
                            if (submitButton.length) {
                                submitButton.prop('disabled', false);
                                submitButton.html(submitButton.data('original-text') || 'Submit');
                            }
                        }
                    });
                }
            });
            
            function showMessage(message, type) {
                var alertContainer = $('.alert-container');
                if (alertContainer.length === 0) {
                    alertContainer = $('<div class="alert-container"></div>');
                    $('body').append(alertContainer);
                }
                
                var alert = $('<div class="alert alert-' + type + ' alert-dismissible fade show" role="alert"></div>');
                alert.html(message + '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>');
                
                alertContainer.append(alert);
                
                setTimeout(function() {
                    alert.removeClass('show');
                    setTimeout(function() {
                        alert.remove();
                    }, 300);
                }, 5000);
            }
        });
    </script>
</body>
</html>
    """)

with open('templates/login.html', 'w') as f:
    f.write("""
{% extends 'layout.html' %}

{% block title %}Login - Test App{% endblock %}

{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h3 class="text-center">Login</h3>
            </div>
            <div class="card-body">
                <form method="POST" action="{{ url_for('login') }}">
                    <div class="mb-3">
                        <label for="username" class="form-label">Username</label>
                        <input type="text" class="form-control" id="username" name="username" required autofocus>
                    </div>
                    <div class="mb-3">
                        <label for="password" class="form-label">Password</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                    </div>
                    <div class="mb-3 form-check">
                        <input type="checkbox" class="form-check-input" id="remember" name="remember">
                        <label class="form-check-label" for="remember">Remember me</label>
                    </div>
                    <div class="d-grid">
                        <button type="submit" class="btn btn-primary">Login</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
    """)

with open('templates/dashboard.html', 'w') as f:
    f.write("""
{% extends 'layout.html' %}

{% block title %}Dashboard - Test App{% endblock %}

{% block content %}
<div class="row">
    <div class="col-12">
        <h1>Dashboard</h1>
        <p>Welcome, {{ current_user.username }}!</p>
        <p>You are logged in successfully.</p>
        <a href="{{ url_for('logout') }}" class="btn btn-danger">Logout</a>
    </div>
</div>
{% endblock %}
    """)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5050)
EOF

print_info "Setting up virtual environment and installing dependencies"
python3 -m venv venv
source venv/bin/activate
pip install flask flask-login flask-socketio gevent gevent-websocket beautifulsoup4

print_header "Testing Login Redirect Fix"
print_info "Starting test application..."
python app.py > app.log 2>&1 &
APP_PID=$!
sleep 5

if ps -p $APP_PID > /dev/null; then
    print_info "✅ Test application started successfully"
    
    print_info "Testing login functionality with curl..."
    
    RESPONSE=$(curl -s -c cookies.txt http://127.0.0.1:5050/login)
    
    LOGIN_RESPONSE=$(curl -s -b cookies.txt -c cookies.txt \
        -H "X-Requested-With: XMLHttpRequest" \
        -d "username=admin&password=admin" \
        -X POST http://127.0.0.1:5050/login)
    
    echo "Login response: $LOGIN_RESPONSE"
    
    if echo "$LOGIN_RESPONSE" | grep -q '"redirect":'; then
        print_info "✅ Login response contains redirect field"
        REDIRECT_URL=$(echo "$LOGIN_RESPONSE" | grep -o '"redirect":"[^"]*"' | cut -d'"' -f4)
        print_info "Redirect URL: $REDIRECT_URL"
        
        DASHBOARD_RESPONSE=$(curl -s -b cookies.txt -c cookies.txt \
            -H "X-Requested-With: XMLHttpRequest" \
            "$REDIRECT_URL")
        
        if echo "$DASHBOARD_RESPONSE" | grep -q "Welcome"; then
            print_info "✅ Successfully redirected to dashboard"
        else
            print_warning "❌ Failed to redirect to dashboard"
        fi
    else
        print_warning "❌ Login response does not contain redirect field"
    fi
    
    print_info "Checking application logs for redirect handling..."
    if grep -q "Converting redirect response to JSON for AJAX request" app.log; then
        print_info "✅ Found log entry for redirect conversion"
        grep "Converting redirect response to JSON for AJAX request" app.log
    else
        print_warning "❌ No log entry found for redirect conversion"
    fi
    
    kill $APP_PID
else
    print_error "❌ Test application failed to start"
    cat app.log
fi

print_header "Test Results"
print_info "The login redirect fix test has completed"
print_info "Check the logs above for any errors or warnings"

print_header "Cleaning up"
deactivate
cd /tmp
rm -rf "$TEST_DIR"

exit 0
