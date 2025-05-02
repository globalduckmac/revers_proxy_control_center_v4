
echo "Setting up Reverse Proxy Control Center v4..."

if [ -z "$VIRTUAL_ENV" ]; then
    echo "No active virtual environment detected."
    
    if [ -d "venv" ]; then
        echo "Using existing virtual environment..."
        source venv/bin/activate
    else
        echo "Creating new virtual environment..."
        python3 -m venv venv
        source venv/bin/activate
    fi
    
    USING_VENV=true
else
    echo "Using active virtual environment: $VIRTUAL_ENV"
    USING_VENV=true
fi

echo "Installing dependencies..."
if [ "$USING_VENV" = true ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "ERROR: Could not set up virtual environment. Please run this script in a virtual environment."
    exit 1
fi

if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "Please update the .env file with your specific configuration."
else
    echo ".env file already exists."
fi

if [ -n "$DATABASE_URL" ]; then
    echo "Database URL found in environment. Checking connection..."
else
    echo "WARNING: DATABASE_URL not found in environment."
    echo "Please set up your database connection in the .env file."
fi

chmod +x *.sh

echo "Setup complete! You can now run the application."

if [ "$USING_VENV" = true ] && [ -z "$VIRTUAL_ENV_DISABLE_PROMPT" ]; then
    deactivate 2>/dev/null || true
fi
