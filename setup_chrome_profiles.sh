#!/bin/bash

# Script to set up Chrome profiles directory for WhatsApp service

# Default directory from config
CHROME_PROFILES_DIR="/opt/chrome-profiles"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Setting up Chrome profiles directory for WhatsApp service...${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (sudo)${NC}"
    exit 1
fi

# Create directory if it doesn't exist
if [ ! -d "$CHROME_PROFILES_DIR" ]; then
    echo "Creating directory: $CHROME_PROFILES_DIR"
    mkdir -p "$CHROME_PROFILES_DIR"
fi

# Set permissions
echo "Setting directory permissions..."
chmod 755 "$CHROME_PROFILES_DIR"

# Get the user running the service (assuming it's the same as the one running Python)
SERVICE_USER=$(ps aux | grep "python" | grep -v "grep" | head -n 1 | awk '{print $1}')

if [ -z "$SERVICE_USER" ]; then
    echo -e "${YELLOW}Could not detect service user, using current user${NC}"
    SERVICE_USER=$SUDO_USER
fi

echo "Setting ownership to $SERVICE_USER"
chown -R $SERVICE_USER:$SERVICE_USER "$CHROME_PROFILES_DIR"

# Install Chrome/Chromium if not present
if ! command -v google-chrome &> /dev/null && ! command -v chromium &> /dev/null; then
    echo -e "${YELLOW}Chrome/Chromium not found. Installing...${NC}"
    
    # Check package manager
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y chromium-browser
    elif command -v dnf &> /dev/null; then
        dnf install -y chromium
    elif command -v yum &> /dev/null; then
        yum install -y chromium
    else
        echo -e "${RED}Could not detect package manager. Please install Chrome/Chromium manually${NC}"
        exit 1
    fi
fi

# Verify installation
if command -v google-chrome &> /dev/null; then
    CHROME_VERSION=$(google-chrome --version)
    echo -e "${GREEN}Google Chrome installed: $CHROME_VERSION${NC}"
elif command -v chromium &> /dev/null; then
    CHROMIUM_VERSION=$(chromium --version || chromium-browser --version)
    echo -e "${GREEN}Chromium installed: $CHROMIUM_VERSION${NC}"
fi

echo -e "${GREEN}Setup completed successfully!${NC}"
echo "Chrome profiles directory: $CHROME_PROFILES_DIR"
echo "Owner: $(stat -c '%U:%G' $CHROME_PROFILES_DIR)"
echo "Permissions: $(stat -c '%a' $CHROME_PROFILES_DIR)"