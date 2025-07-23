#!/bin/bash

# RStudio Launchpad Daemon Setup Script for Ubuntu
# This script sets up systemd services to automatically clean up expired RStudio sessions

set -e

echo "Setting up RStudio Session Cleanup Daemon on Ubuntu..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script as root (sudo)"
    exit 1
fi

# Configuration variables
INSTALL_PATH="/opt/rstudio-portal"
SERVICE_USER="rstudio-daemon"
LOG_DIR="/var/log/rstudio-portal"

# Create installation directory
echo "Creating installation directory..."
mkdir -p $INSTALL_PATH
mkdir -p $LOG_DIR

# Create dedicated user for the service (optional but recommended)
if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Creating service user: $SERVICE_USER"
    useradd --system --shell /bin/false --home-dir $INSTALL_PATH --create-home $SERVICE_USER
    usermod -aG docker $SERVICE_USER  # Add to docker group to manage containers
fi

# Copy application files
echo "Copying application files to $INSTALL_PATH..."
cp -r /path/to/your/rstudio-launchpad/* $INSTALL_PATH/
chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_PATH

# Set up Python environment
echo "Setting up Python environment..."
apt-get update
apt-get install -y python3 python3-pip python3-venv

# Create virtual environment
cd $INSTALL_PATH
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Make scripts executable
chmod +x $INSTALL_PATH/scripts/cleanup_expired_instances.py
chmod +x $INSTALL_PATH/docker_templates/cleanup_expired.sh

# Copy systemd service files
echo "Installing systemd service files..."
cp $INSTALL_PATH/systemd/rstudio-cleanup.service /etc/systemd/system/
cp $INSTALL_PATH/systemd/rstudio-cleanup.timer /etc/systemd/system/

# Update service file with correct paths and user
sed -i "s|/opt/rstudio-portal|$INSTALL_PATH|g" /etc/systemd/system/rstudio-cleanup.service
sed -i "s|User=root|User=$SERVICE_USER|g" /etc/systemd/system/rstudio-cleanup.service
sed -i "s|Group=root|Group=$SERVICE_USER|g" /etc/systemd/system/rstudio-cleanup.service

# Set proper permissions
chown $SERVICE_USER:$SERVICE_USER $LOG_DIR
chmod 755 $LOG_DIR

# Reload systemd and enable services
echo "Enabling and starting systemd services..."
systemctl daemon-reload
systemctl enable rstudio-cleanup.service
systemctl enable rstudio-cleanup.timer
systemctl start rstudio-cleanup.timer

# Check status
echo "Checking service status..."
systemctl status rstudio-cleanup.timer --no-pager

echo ""
echo "✅ RStudio Session Cleanup Daemon has been successfully set up!"
echo ""
echo "Service details:"
echo "- Service name: rstudio-cleanup"
echo "- Timer name: rstudio-cleanup.timer"
echo "- Runs every: 5 minutes"
echo "- User: $SERVICE_USER"
echo "- Install path: $INSTALL_PATH"
echo "- Log directory: $LOG_DIR"
echo ""
echo "Useful commands:"
echo "- Check timer status: systemctl status rstudio-cleanup.timer"
echo "- Check service logs: journalctl -u rstudio-cleanup.service -f"
echo "- Manually run cleanup: systemctl start rstudio-cleanup.service"
echo "- Stop timer: systemctl stop rstudio-cleanup.timer"
echo "- Restart timer: systemctl restart rstudio-cleanup.timer"
echo ""
echo "To modify the cleanup interval, edit /etc/systemd/system/rstudio-cleanup.timer"
echo "and run 'systemctl daemon-reload && systemctl restart rstudio-cleanup.timer'"
