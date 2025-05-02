#!/bin/bash

# Deployment script for Reverse Proxy Control Center v4
# This script automates the full installation and deployment process on Ubuntu 22.04

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Output functions
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

# Check for root privileges
if [ "$(id -u)" != "0" ]; then
   print_error "This script must be run with root privileges (sudo)"
   exit 1
fi

# Initial parameters
APP_DIR="/opt/reverse_proxy_control_center"
SERVER_IP=$(hostname -I | awk '{print $1}')
ENCRYPTION_KEY=$(openssl rand -hex 32)
SESSION_SECRET=$(openssl rand -hex 32)
ADMIN_PASSWORD=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9')
DB_PASSWORD=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9')
REPO_URL="https://github.com/globalduckmac/revers_proxy_control_center_v4.git"
BRANCH="implementation/fix-proxy-center"

print_header "Reverse Proxy Control Center v4 - Installation"
print_info "Server: $SERVER_IP"
print_info "Installation directory: $APP_DIR"
print_info "Repository: $REPO_URL"
print_info "Branch: $BRANCH"

# Install system dependencies
print_header "Installing system dependencies"
apt update
apt install -y git python3 python3-pip python3-venv python3-dev nginx postgresql postgresql-contrib \
    curl apt-transport-https ca-certificates libpq-dev build-essential libssl-dev libffi-dev

# Create application directory
print_header "Preparing filesystem"
mkdir -p "$APP_DIR"
mkdir -p /var/log/reverse_proxy_control_center

# Clone repository
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

# Set up PostgreSQL
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

# Set up Python virtual environment
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

# Create .env file
print_header "Creating environment configuration"
if [ -f "$APP_DIR/.env" ]; then
    print_info ".env file already exists. Creating backup..."
    cp "$APP_DIR/.env" "$APP_DIR/.env.backup.$(date +%s)"
fi

cat > "$APP_DIR/.env" << EOF
# Environment variables for the application
# Created by deploy.sh on $(date)

# Flask configuration
FLASK_ENV=production

# Security keys
ENCRYPTION_KEY=$ENCRYPTION_KEY
SESSION_SECRET=$SESSION_SECRET

# Database configuration
DATABASE_URL=postgresql://rpcc:$DB_PASSWORD@localhost/rpcc

# Email settings
ADMIN_EMAIL=admin@example.com

# SSH connection settings
SSH_TIMEOUT=60
SSH_COMMAND_TIMEOUT=600
EOF

print_header "Running setup script"
cd "$APP_DIR"
chmod +x setup.sh
./setup.sh

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

# Check Nginx configuration
print_info "Checking Nginx configuration..."
nginx -t
if [ $? -ne 0 ]; then
    print_error "Error in Nginx configuration. Please check and fix errors."
    exit 1
fi

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
ExecStartPre=/bin/sleep 2
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 --timeout 120 --access-logfile /var/log/reverse_proxy_control_center/access.log --error-logfile /var/log/reverse_proxy_control_center/error.log main:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

print_header "Starting services"
systemctl daemon-reload
systemctl enable reverse_proxy_control_center.service
systemctl restart nginx
systemctl restart reverse_proxy_control_center.service

print_info "Waiting for services to start (10 seconds)..."
sleep 10

print_header "Service status"
systemctl status postgresql --no-pager
systemctl status nginx --no-pager
systemctl status reverse_proxy_control_center --no-pager

# Create admin user
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
        # Create admin user
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
