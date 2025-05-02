#!/bin/bash

# Test script for deploy.sh
# This script validates the deploy.sh script without making system changes

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Testing deploy.sh script...${NC}"

# Check if deploy.sh exists
if [ ! -f deploy.sh ]; then
    echo -e "${RED}Error: deploy.sh not found${NC}"
    exit 1
fi

# Check script syntax
echo "Checking script syntax..."
bash -n deploy.sh
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: deploy.sh has syntax errors${NC}"
    exit 1
fi
echo -e "${GREEN}Syntax check passed${NC}"

# Check for required components
echo "Checking for required components..."

# System dependencies
if ! grep -q "apt install" deploy.sh; then
    echo -e "${RED}Error: Missing system dependencies installation${NC}"
    exit 1
fi
echo -e "${GREEN}System dependencies check passed${NC}"

# Repository cloning
if ! grep -q "git clone" deploy.sh; then
    echo -e "${RED}Error: Missing repository cloning${NC}"
    exit 1
fi
echo -e "${GREEN}Repository cloning check passed${NC}"

# Virtual environment setup
if ! grep -q "python3 -m venv" deploy.sh; then
    echo -e "${RED}Error: Missing virtual environment setup${NC}"
    exit 1
fi
echo -e "${GREEN}Virtual environment setup check passed${NC}"

# .env file creation
if ! grep -q "cat > \"\$APP_DIR/.env\"" deploy.sh; then
    echo -e "${RED}Error: Missing .env file creation${NC}"
    exit 1
fi
echo -e "${GREEN}.env file creation check passed${NC}"

# Database setup
if ! grep -q "CREATE DATABASE rpcc" deploy.sh; then
    echo -e "${RED}Error: Missing database setup${NC}"
    exit 1
fi
echo -e "${GREEN}Database setup check passed${NC}"

# Service configuration
if ! grep -q "/etc/systemd/system/reverse_proxy_control_center.service" deploy.sh; then
    echo -e "${RED}Error: Missing service configuration${NC}"
    exit 1
fi
echo -e "${GREEN}Service configuration check passed${NC}"

# Application startup
if ! grep -q "systemctl restart reverse_proxy_control_center" deploy.sh; then
    echo -e "${RED}Error: Missing application startup${NC}"
    exit 1
fi
echo -e "${GREEN}Application startup check passed${NC}"

echo -e "${GREEN}All checks passed. The deploy.sh script appears to be valid.${NC}"
echo ""
echo "To deploy on a fresh Ubuntu 22.04 server, run:"
echo "wget -O deploy.sh https://raw.githubusercontent.com/globalduckmac/revers_proxy_control_center_v4/implementation/fix-proxy-center/deploy.sh && sudo bash deploy.sh"

exit 0
