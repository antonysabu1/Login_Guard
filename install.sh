#!/bin/bash

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit
fi

INSTALL_DIR="/opt/login_guard"

echo "Installing Login Guard..."

# Create directory
mkdir -p "$INSTALL_DIR"
cp login_guard.py "$INSTALL_DIR/"
cp requirements.txt "$INSTALL_DIR/"

# Only create .env if it doesn't exist (preserve user config on update)
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp .env.example "$INSTALL_DIR/.env"
fi

# Set up virtual environment
echo "Setting up virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Install service
echo "Installing systemd service..."
cp login_guard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable login_guard
systemctl start login_guard

echo " Installation Complete!"
echo "------------------------------------------------"
echo "1. Edit the configuration file with your Telegram keys:"
echo "   sudo nano $INSTALL_DIR/.env"
echo ""
echo "2. Restart the service to apply changes:"
echo "   sudo systemctl restart login_guard"
echo "------------------------------------------------"
