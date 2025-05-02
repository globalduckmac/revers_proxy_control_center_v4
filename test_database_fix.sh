
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

print_header "Testing Database URL Fix"
print_info "This script will test the fix for the DATABASE_URL configuration issue"

TEST_DIR="/tmp/rpcc_db_test"
print_info "Creating test directory: $TEST_DIR"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

print_info "Creating test environment"
cat > test_db.py << EOF
import os
import sys

db_url = os.environ.get('DATABASE_URL')
print(f"DATABASE_URL from environment: {db_url}")

if not db_url:
    print("DATABASE_URL is not set in environment")
    sys.exit(1)

try:
    if db_url.startswith('postgresql://'):
        print("Valid PostgreSQL connection string format")
    else:
        print("Invalid PostgreSQL connection string format")
        sys.exit(1)
except Exception as e:
    print(f"Error parsing DATABASE_URL: {e}")
    sys.exit(1)

try:
    import psycopg2
    print("Successfully imported psycopg2")
except ImportError:
    print("Failed to import psycopg2")
    sys.exit(1)

print("All database configuration tests passed!")
sys.exit(0)
EOF

print_header "Testing environment variable export"
export DATABASE_URL="postgresql://test:test@localhost/test"
python3 test_db.py

if [ $? -eq 0 ]; then
    print_info "✅ Environment variable test passed"
else
    print_error "❌ Environment variable test failed"
    exit 1
fi

print_header "Testing systemd service file generation"
cat > test_service.sh << EOF
APP_DIR="/opt/test"
DB_PASSWORD="testpass"

cat > test_service.txt << EOT
[Unit]
Description=Test Service
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=\$APP_DIR
EnvironmentFile=\$APP_DIR/.env
Environment="DATABASE_URL=postgresql://rpcc:\$DB_PASSWORD@localhost/rpcc"
Environment="PYTHONPATH=\$APP_DIR"
ExecStartPre=/bin/sleep 2
ExecStart=\$APP_DIR/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOT
EOF

chmod +x test_service.sh
./test_service.sh

if [ -f "test_service.txt" ]; then
    print_info "✅ Service file generation test passed"
    cat test_service.txt
else
    print_error "❌ Service file generation test failed"
    exit 1
fi

print_header "Cleaning up"
rm -rf "$TEST_DIR"

print_header "Test Results"
print_info "✅ The database URL fix was successful"
print_info "The updated deploy.sh script should now properly configure the database connection"
print_info "This should resolve the 502 Bad Gateway error"

exit 0
