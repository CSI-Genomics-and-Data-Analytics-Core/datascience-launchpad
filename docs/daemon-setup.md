# RStudio Session Cleanup Daemon

This directory contains the necessary files to set up a Linux daemon on Ubuntu that automatically cleans up expired RStudio sessions and updates the database.

## Overview

The daemon uses systemd to run cleanup tasks at regular intervals. It consists of:

1. **Python cleanup script** (`scripts/cleanup_expired_instances.py`) - Main cleanup logic
2. **Bash cleanup script** (`scripts/cleanup_daemon.sh`) - Alternative bash implementation
3. **Systemd service** (`systemd/rstudio-cleanup.service`) - Service definition
4. **Systemd timer** (`systemd/rstudio-cleanup.timer`) - Scheduling timer
5. **Setup script** (`scripts/setup_daemon.sh`) - Automated installation
6. **Management script** (`scripts/manage_daemon.sh`) - Easy service management

## Features

- **Automatic cleanup**: Runs every 1 hour by default
- **Database integration**: Updates instance status in SQLite database
- **Docker management**: Stops and removes expired containers
- **Comprehensive logging**: Detailed logs for monitoring and debugging
- **Security**: Runs with minimal privileges
- **Error handling**: Robust error handling and recovery
- **Easy management**: Simple commands to control the daemon

## Quick Setup

### 1. Install the Daemon

```bash
# Make scripts executable
chmod +x scripts/setup_daemon.sh scripts/manage_daemon.sh scripts/cleanup_daemon.sh

# Install the daemon (requires root)
sudo ./scripts/setup_daemon.sh
```

### 2. Verify Installation

```bash
# Check daemon status
./scripts/manage_daemon.sh status

# View recent logs
./scripts/manage_daemon.sh logs
```

## Manual Installation Steps

If you prefer to install manually:

### 1. Prepare the Environment

```bash
# Update system
sudo apt-get update
sudo apt-get install -y python3 python3-pip sqlite3

# Create application directory
sudo mkdir -p /opt/rstudio-portal
sudo cp -r * /opt/rstudio-portal/

# Create logs directory
sudo mkdir -p /var/log/rstudio-portal

# Install Python dependencies
cd /opt/rstudio-portal
sudo pip3 install -r requirements.txt
```

### 2. Create Service User (Recommended)

```bash
# Create dedicated user for the service
sudo useradd --system --shell /bin/false --home-dir /opt/rstudio-portal rstudio-daemon
sudo usermod -aG docker rstudio-daemon

# Set permissions
sudo chown -R rstudio-daemon:rstudio-daemon /opt/rstudio-portal
sudo chown rstudio-daemon:rstudio-daemon /var/log/rstudio-portal
```

### 3. Install Systemd Services

```bash
# Copy service files
sudo cp systemd/rstudio-cleanup.service /etc/systemd/system/
sudo cp systemd/rstudio-cleanup.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start services
sudo systemctl enable rstudio-cleanup.service
sudo systemctl enable rstudio-cleanup.timer
sudo systemctl start rstudio-cleanup.timer
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Database configuration
DB_MOUNT_PATH=/opt/rstudio-portal
DATABASE_FILENAME=db.sqlite3

# Logging level
LOG_LEVEL=INFO
```

### Timer Interval

To change the cleanup interval, edit `/etc/systemd/system/rstudio-cleanup.timer`:

```ini
[Timer]
OnBootSec=5min
OnUnitActiveSec=1h  # Change this line (e.g., 10min, 1h, 30s)
Unit=rstudio-cleanup.service
```

After editing, reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart rstudio-cleanup.timer
```

## Management Commands

Use the management script for easy control:

```bash
# Start the cleanup daemon
./scripts/manage_daemon.sh start

# Stop the cleanup daemon
./scripts/manage_daemon.sh stop

# Restart the cleanup daemon
./scripts/manage_daemon.sh restart

# Check status
./scripts/manage_daemon.sh status

# View logs
./scripts/manage_daemon.sh logs

# Enable automatic startup
./scripts/manage_daemon.sh enable

# Disable automatic startup
./scripts/manage_daemon.sh disable

# Run cleanup manually once
./scripts/manage_daemon.sh test

# Uninstall daemon
./scripts/manage_daemon.sh uninstall
```

## Monitoring and Logs

### View Service Logs

```bash
# Recent logs
journalctl -u rstudio-cleanup.service -n 50

# Follow logs in real-time
journalctl -u rstudio-cleanup.service -f

# Logs from specific time
journalctl -u rstudio-cleanup.service --since "2024-01-01 10:00:00"
```

### Check Timer Status

```bash
# List all timers
systemctl list-timers

# Specific timer info
systemctl status rstudio-cleanup.timer
```

### Log Files

- Service logs: `/var/log/rstudio-portal/cleanup.log`
- System logs: `journalctl -u rstudio-cleanup.service`

## Security Considerations

1. **Dedicated User**: Runs under a dedicated system user with minimal privileges
2. **Docker Group**: Service user needs docker group membership to manage containers
3. **File Permissions**: Restricted file system access
4. **No Network**: Service doesn't require network access
5. **Read-only System**: Uses `ProtectSystem=strict` in systemd

## Troubleshooting

### Common Issues

1. **Permission Denied**
   ```bash
   # Check user permissions
   sudo usermod -aG docker rstudio-daemon
   ```

2. **Database Lock**
   ```bash
   # Check database permissions
   sudo chown rstudio-daemon:rstudio-daemon /opt/rstudio-portal/db.sqlite3
   ```

3. **Docker Not Accessible**
   ```bash
   # Ensure Docker is running
   sudo systemctl status docker
   ```

4. **Service Won't Start**
   ```bash
   # Check service configuration
   sudo systemctl status rstudio-cleanup.service
   journalctl -u rstudio-cleanup.service
   ```

### Debug Mode

Run cleanup manually for debugging:

```bash
# Run Python script directly
cd /opt/rstudio-portal
python3 scripts/cleanup_expired_instances.py

# Run bash script directly
bash scripts/cleanup_daemon.sh
```

## File Structure

```
rstudio-launchpad/
├── scripts/
│   ├── cleanup_expired_instances.py  # Main Python cleanup script
│   ├── cleanup_daemon.sh            # Bash cleanup script
│   ├── setup_daemon.sh              # Automated installation
│   └── manage_daemon.sh             # Service management
├── systemd/
│   ├── rstudio-cleanup.service      # Systemd service definition
│   └── rstudio-cleanup.timer        # Systemd timer definition
└── docs/
    └── daemon-setup.md              # This documentation
```

## What the Daemon Does

1. **Queries Database**: Finds instances with `status='running'` and `expires_at < now()`
2. **Stops Containers**: Uses `docker stop` to gracefully stop expired containers
3. **Removes Containers**: Uses `docker rm` to clean up stopped containers
4. **Updates Database**: Sets instance status to `stopped_expired` or `expired_cleaned`
5. **Logs Actions**: Records all actions for audit and debugging
6. **Error Handling**: Continues processing even if individual containers fail

## Integration with Main Application

The daemon works alongside your main RStudio launchpad application:

- **Database Sync**: Updates the same SQLite database used by the web application
- **Container Management**: Uses the same Docker daemon as the main application
- **User Data**: Preserves user data in `/user_data/` directories
- **Logging**: Separate logs to avoid conflicts with main application logs

This setup ensures expired sessions are automatically cleaned up without manual intervention while maintaining data integrity and system security.
