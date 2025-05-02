
echo "Setting up Reverse Proxy Control Center v4..."

echo "Installing dependencies..."
pip install -r requirements.txt

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
