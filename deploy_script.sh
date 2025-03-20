#!/bin/bash

# Automated deployment script for Reverse Proxy Manager
# This script installs all dependencies and sets up the application on Ubuntu

# Exit on any error
set -e

echo "=== Starting Reverse Proxy Manager Deployment ==="

# Update system packages
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install required system packages
echo "Installing required system packages..."
sudo apt-get install -y python3 python3-pip python3-venv mysql-server nginx

# Configure MySQL
echo "Configuring MySQL..."
sudo mysql_secure_installation

# Create database and user
echo "Creating database and user..."
echo "Please enter your MySQL root password:"
read -s MYSQL_ROOT_PASSWORD

# Create database and user
sudo mysql -u root -p"$MYSQL_ROOT_PASSWORD" <<EOF
CREATE DATABASE IF NOT EXISTS reverse_proxy_manager;
CREATE USER IF NOT EXISTS 'proxy_manager'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON reverse_proxy_manager.* TO 'proxy_manager'@'localhost';
FLUSH PRIVILEGES;
EOF

# Create application directory
APP_DIR="/opt/reverse-proxy-manager"
echo "Creating application directory at $APP_DIR..."
sudo mkdir -p "$APP_DIR"
sudo chown $USER:$USER "$APP_DIR"

# Clone repository (assuming code is in a repository)
# echo "Cloning application repository..."
# git clone https://github.com/your-repo/reverse-proxy-manager.git "$APP_DIR"

# If not using git, copy files manually
# echo "Copying application files..."
# cp -R . "$APP_DIR"

# Set up Python virtual environment
echo "Setting up Python virtual environment..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install flask flask-sqlalchemy flask-login pymysql paramiko jinja2 cryptography

# Set up environment variables
echo "Setting up environment variables..."
cat > "$APP_DIR/.env" <<EOF
FLASK_APP=main.py
FLASK_ENV=production
SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(24))")
DATABASE_URL=mysql://proxy_manager:secure_password@localhost/reverse_proxy_manager
EOF

# Create systemd service file
echo "Creating systemd service..."
sudo tee /etc/systemd/system/reverse-proxy-manager.service > /dev/null <<EOF
[Unit]
Description=Reverse Proxy Manager
After=network.target mysql.service

[Service]
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python3 main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
echo "Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable reverse-proxy-manager
sudo systemctl start reverse-proxy-manager

# Set up Nginx as a reverse proxy to the application
echo "Setting up Nginx reverse proxy..."
sudo tee /etc/nginx/sites-available/reverse-proxy-manager > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

# Enable site and restart Nginx
sudo ln -sf /etc/nginx/sites-available/reverse-proxy-manager /etc/nginx/sites-enabled/
sudo systemctl restart nginx

echo "=== Deployment completed! ==="
echo "Reverse Proxy Manager is now running at http://YOUR_SERVER_IP"
echo "You can create an admin user by running: source $APP_DIR/venv/bin/activate && python -c 'from app import app; from models import User, db; with app.app_context(): user = User(username=\"admin\", email=\"admin@example.com\", is_admin=True); user.set_password(\"admin_password\"); db.session.add(user); db.session.commit()'"
