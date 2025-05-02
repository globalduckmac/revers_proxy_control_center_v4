
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

if [ "$(id -u)" != "0" ]; then
   print_error "This script must be run with root privileges (sudo)"
   exit 1
fi

APP_DIR="/opt/reverse_proxy_control_center"
SERVER_IP=$(hostname -I | awk '{print $1}')
ENCRYPTION_KEY=$(openssl rand -hex 32)
SESSION_SECRET=$(openssl rand -hex 32)
ADMIN_PASSWORD=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9')
DB_PASSWORD=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9')
REPO_URL="https://github.com/globalduckmac/revers_proxy_control_center_v4.git"
BRANCH="devin/1746202003-ssl-spa-enhancements"

print_header "Reverse Proxy Control Center v4 - Installation"
print_info "Server: $SERVER_IP"
print_info "Installation directory: $APP_DIR"
print_info "Repository: $REPO_URL"
print_info "Branch: $BRANCH"

print_header "Installing system dependencies"
apt update
apt install -y git python3 python3-pip python3-venv python3-dev nginx postgresql postgresql-contrib \
    curl apt-transport-https ca-certificates libpq-dev build-essential libssl-dev libffi-dev

print_header "Preparing filesystem"
mkdir -p "$APP_DIR"
mkdir -p /var/log/reverse_proxy_control_center

print_header "Cloning repository"
if [ -d "$APP_DIR/.git" ]; then
    print_info "Repository already exists. Updating..."
    cd "$APP_DIR"
    git fetch --all
    git checkout $BRANCH
    git pull origin $BRANCH
else
    print_info "Cloning repository..."
    rm -rf "$APP_DIR"/*
    git clone -b $BRANCH $REPO_URL "$APP_DIR"
fi

print_header "Setting up PostgreSQL"
print_info "Checking PostgreSQL status..."
if ! systemctl is-active --quiet postgresql; then
    print_info "Starting PostgreSQL..."
    systemctl start postgresql
    systemctl enable postgresql
fi

print_info "Setting up database..."
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='rpcc'" | grep -q 1; then
    print_info "Database user 'rpcc' already exists"
else
    print_info "Creating database user 'rpcc'..."
    sudo -u postgres psql -c "CREATE USER rpcc WITH PASSWORD '$DB_PASSWORD';"
fi

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='rpcc'" | grep -q 1; then
    print_info "Database 'rpcc' already exists"
else
    print_info "Creating database 'rpcc'..."
    sudo -u postgres psql -c "CREATE DATABASE rpcc OWNER rpcc;"
fi

print_header "Setting up Python virtual environment"
cd "$APP_DIR"

if [ -d "$APP_DIR/venv" ]; then
    print_info "Virtual environment already exists. Updating..."
else
    print_info "Creating virtual environment..."
    python3 -m venv venv
fi

print_info "Installing Python dependencies..."
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r requirements.txt

print_header "Creating environment configuration"
if [ -f "$APP_DIR/.env" ]; then
    print_info ".env file already exists. Creating backup..."
    cp "$APP_DIR/.env" "$APP_DIR/.env.backup.$(date +%s)"
fi

cat > "$APP_DIR/.env" << EOF
FLASK_ENV=production
ENCRYPTION_KEY=$ENCRYPTION_KEY
SESSION_SECRET=$SESSION_SECRET
DATABASE_URL=postgresql://rpcc:$DB_PASSWORD@localhost/rpcc
ADMIN_EMAIL=admin@example.com
SSH_TIMEOUT=60
SSH_COMMAND_TIMEOUT=600
EOF

print_info "Verifying database connection..."
export DATABASE_URL="postgresql://rpcc:$DB_PASSWORD@localhost/rpcc"
cd "$APP_DIR"
if [ -f "$APP_DIR/venv/bin/python" ]; then
    "$APP_DIR/venv/bin/python" -c "
import sys
import psycopg2
try:
    conn = psycopg2.connect('$DATABASE_URL')
    print('Database connection successful')
    conn.close()
except Exception as e:
    print('Database connection failed:', e)
    sys.exit(1)
"
    if [ $? -ne 0 ]; then
        print_error "Database connection failed. Please check your PostgreSQL configuration."
        print_info "Attempting to fix database connection..."
        sudo -u postgres psql -c "ALTER USER rpcc WITH PASSWORD '$DB_PASSWORD';"
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE rpcc TO rpcc;"
    else
        print_info "Database connection verified successfully."
    fi
else
    print_warning "Python virtual environment not found. Skipping database verification."
fi

print_header "Running setup script"
cd "$APP_DIR"
chmod +x setup.sh

print_info "Setting up Reverse Proxy Control Center v4..."
source "$APP_DIR/venv/bin/activate"
export DATABASE_URL="postgresql://rpcc:$DB_PASSWORD@localhost/rpcc"
./setup.sh

print_info "Initializing database..."
python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('Database tables created successfully')
" || print_warning "Database initialization failed. Tables may already exist."

deactivate

print_header "Setting permissions"
chown -R www-data:www-data "$APP_DIR"
chmod -R 755 "$APP_DIR"
chown -R www-data:www-data /var/log/reverse_proxy_control_center

print_header "Setting up Nginx"
cat > /etc/nginx/sites-available/reverse_proxy_control_center << EOF
server {
    listen 80;
    server_name $SERVER_IP;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

if [ -f /etc/nginx/sites-enabled/reverse_proxy_control_center ]; then
    print_info "Nginx configuration already enabled"
else
    ln -s /etc/nginx/sites-available/reverse_proxy_control_center /etc/nginx/sites-enabled/
    print_info "Nginx configuration enabled successfully"
fi

print_info "Checking Nginx configuration..."
nginx -t
if [ $? -ne 0 ]; then
    print_error "Error in Nginx configuration. Please check and fix errors."
    exit 1
fi

print_header "Detecting application entry point"
cd "$APP_DIR"

APP_MODULE="app:app"
if [ -f "$APP_DIR/main.py" ]; then
    print_info "Found main.py, checking if it should be used as entry point..."
    grep -q "from app import app" "$APP_DIR/main.py"
    if [ $? -eq 0 ]; then
        print_info "main.py imports app, will try it as primary entry point"
        APP_MODULE="main:app"
    fi
fi

print_info "Using $APP_MODULE as application entry point"

cat > "$APP_DIR/test_app_import.py" << EOF
import sys
import importlib.util

try:
    module_name, object_name = "$APP_MODULE".split(':')
    spec = importlib.util.spec_from_file_location(module_name, "$APP_DIR/{}.py".format(module_name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app_object = getattr(module, object_name)
    print("Successfully imported {}".format("$APP_MODULE"))
    sys.exit(0)
except Exception as e:
    print("Error importing {}: {}".format("$APP_MODULE", e))
    sys.exit(1)
EOF

"$APP_DIR/venv/bin/python" "$APP_DIR/test_app_import.py"
if [ $? -ne 0 ]; then
    print_warning "Failed to import $APP_MODULE, falling back to alternative"
    if [ "$APP_MODULE" = "app:app" ]; then
        APP_MODULE="main:app"
    else
        APP_MODULE="app:app"
    fi
    print_info "Trying alternative entry point: $APP_MODULE"
fi

rm -f "$APP_DIR/test_app_import.py"

print_header "Creating systemd service"
cat > /etc/systemd/system/reverse_proxy_control_center.service << EOF
[Unit]
Description=Reverse Proxy Control Center v4
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment="DATABASE_URL=postgresql://rpcc:$DB_PASSWORD@localhost/rpcc"
Environment="PYTHONPATH=$APP_DIR"
Environment="FLASK_APP=$APP_DIR/app.py"
ExecStartPre=/bin/sleep 2
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 --timeout 120 --access-logfile /var/log/reverse_proxy_control_center/access.log --error-logfile /var/log/reverse_proxy_control_center/error.log --log-level debug $APP_MODULE
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

print_header "Starting services"
systemctl daemon-reload
systemctl enable reverse_proxy_control_center.service
systemctl restart nginx

print_info "Installing additional dependencies for WebSockets..."
"$APP_DIR/venv/bin/pip" install flask-socketio eventlet gunicorn==20.1.0

print_info "Installing additional dependencies for Telegram notifications..."
"$APP_DIR/venv/bin/pip" install urllib3==1.26.15
"$APP_DIR/venv/bin/pip" install python-telegram-bot==13.15

print_info "Creating debug wrapper for application..."
cat > "$APP_DIR/wsgi.py" << EOF
import os
import sys
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/var/log/reverse_proxy_control_center/debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('wsgi')

sys.path.insert(0, os.path.dirname(__file__))

try:
    logger.info("Attempting to import app from main module")
    from main import app as application
    logger.info("Successfully imported app from main module")
except Exception as e:
    logger.error(f"Error importing from main: {str(e)}")
    try:
        logger.info("Attempting to import app from app module")
        from app import app as application
        logger.info("Successfully imported app from app module")
    except Exception as e:
        logger.error(f"Error importing from app: {str(e)}")
        raise

env_vars = {k: v for k, v in os.environ.items() 
            if not any(sensitive in k.lower() for sensitive in 
                      ['password', 'secret', 'key', 'token'])}
logger.debug(f"Environment variables: {env_vars}")

logger.info(f"Application object: {application}")

app = application
EOF

print_info "Starting application service..."
systemctl daemon-reload
systemctl restart reverse_proxy_control_center.service

print_info "Waiting for services to start (15 seconds)..."
sleep 15

if ! systemctl is-active --quiet reverse_proxy_control_center; then
    print_warning "Service failed to start. Checking logs..."
    journalctl -u reverse_proxy_control_center -n 50 --no-pager
    
    print_info "Attempting to fix service configuration with eventlet worker..."
    cat > /etc/systemd/system/reverse_proxy_control_center.service << EOF
[Unit]
Description=Reverse Proxy Control Center v4
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment="DATABASE_URL=postgresql://rpcc:$DB_PASSWORD@localhost/rpcc"
Environment="PYTHONPATH=$APP_DIR"
Environment="FLASK_APP=$APP_DIR/app.py"
ExecStartPre=/bin/sleep 2
ExecStart=$APP_DIR/venv/bin/gunicorn --worker-class eventlet --workers 1 --bind 0.0.0.0:5000 --timeout 120 --access-logfile /var/log/reverse_proxy_control_center/access.log --error-logfile /var/log/reverse_proxy_control_center/error.log --log-level debug wsgi:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl restart reverse_proxy_control_center.service
    sleep 10
    
    if ! systemctl is-active --quiet reverse_proxy_control_center; then
        print_warning "Service still failed to start. Trying direct Flask run..."
        
        cat > "$APP_DIR/run_flask.sh" << EOF
#!/bin/bash
cd $APP_DIR
source venv/bin/activate
export FLASK_APP=app.py
export FLASK_ENV=production
export DATABASE_URL=postgresql://rpcc:$DB_PASSWORD@localhost/rpcc
python -m flask run --host=0.0.0.0 --port=5000 > /var/log/reverse_proxy_control_center/flask.log 2>&1
EOF
        
        chmod +x "$APP_DIR/run_flask.sh"
        
        cat > /etc/systemd/system/reverse_proxy_control_center.service << EOF
[Unit]
Description=Reverse Proxy Control Center v4
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment="DATABASE_URL=postgresql://rpcc:$DB_PASSWORD@localhost/rpcc"
Environment="PYTHONPATH=$APP_DIR"
Environment="FLASK_APP=$APP_DIR/app.py"
ExecStartPre=/bin/sleep 2
ExecStart=$APP_DIR/run_flask.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        
        systemctl daemon-reload
        systemctl restart reverse_proxy_control_center.service
        sleep 10
    fi
fi

print_header "Service status"
systemctl status postgresql --no-pager
systemctl status nginx --no-pager
systemctl status reverse_proxy_control_center --no-pager

print_header "Creating admin user"
cd "$APP_DIR"
cat > create_admin.py << EOF
import sys
import os
from app import create_app
from models import db, User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    
    if admin:
        print("Admin user already exists")
    else:
        admin = User(
            username='admin',
            email='admin@example.com',
            password_hash=generate_password_hash('$ADMIN_PASSWORD'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully")
        print("Username: admin")
        print("Password: $ADMIN_PASSWORD")
EOF

"$APP_DIR/venv/bin/python" create_admin.py
rm create_admin.py

print_header "Installation Complete"
print_info "Reverse Proxy Control Center v4 has been installed successfully!"
print_info "You can access the application at: http://$SERVER_IP"
print_info "Admin username: admin"
print_info "Admin password: $ADMIN_PASSWORD"
print_info "Database password: $DB_PASSWORD"
print_info ""
print_info "To view application logs:"
print_info "  - Access logs: tail -f /var/log/reverse_proxy_control_center/access.log"
print_info "  - Error logs: tail -f /var/log/reverse_proxy_control_center/error.log"
print_info "  - Service logs: journalctl -u reverse_proxy_control_center -f"
print_info ""
print_info "To restart the application:"
print_info "  - sudo systemctl restart reverse_proxy_control_center"
print_info ""
print_info "Please save this information for future reference."

exit 0
