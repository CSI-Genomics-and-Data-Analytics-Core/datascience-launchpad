#!/bin/bash

# Management script for RStudio cleanup daemon
# Provides easy commands to manage the cleanup service

set -e

SERVICE_NAME="rstudio-cleanup"
TIMER_NAME="rstudio-cleanup.timer"

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs|enable|disable|install|uninstall}"
    echo ""
    echo "Commands:"
    echo "  start     - Start the cleanup timer"
    echo "  stop      - Stop the cleanup timer"
    echo "  restart   - Restart the cleanup timer"
    echo "  status    - Show service and timer status"
    echo "  logs      - Show recent logs"
    echo "  enable    - Enable automatic startup"
    echo "  disable   - Disable automatic startup"
    echo "  install   - Install the daemon (requires root)"
    echo "  uninstall - Uninstall the daemon (requires root)"
    echo "  test      - Run cleanup manually once"
    exit 1
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "This command requires root privileges. Please run with sudo."
        exit 1
    fi
}

start_service() {
    echo "Starting RStudio cleanup timer..."
    sudo systemctl start $TIMER_NAME
    echo "✅ Timer started"
}

stop_service() {
    echo "Stopping RStudio cleanup timer..."
    sudo systemctl stop $TIMER_NAME
    echo "✅ Timer stopped"
}

restart_service() {
    echo "Restarting RStudio cleanup timer..."
    sudo systemctl restart $TIMER_NAME
    echo "✅ Timer restarted"
}

show_status() {
    echo "=== Service Status ==="
    sudo systemctl status $SERVICE_NAME --no-pager || true
    echo ""
    echo "=== Timer Status ==="
    sudo systemctl status $TIMER_NAME --no-pager || true
    echo ""
    echo "=== Timer List ==="
    sudo systemctl list-timers $TIMER_NAME --no-pager || true
}

show_logs() {
    echo "=== Recent Service Logs ==="
    sudo journalctl -u $SERVICE_NAME -n 50 --no-pager
    echo ""
    echo "=== Follow logs with: journalctl -u $SERVICE_NAME -f ==="
}

enable_service() {
    echo "Enabling RStudio cleanup service for automatic startup..."
    sudo systemctl enable $SERVICE_NAME
    sudo systemctl enable $TIMER_NAME
    echo "✅ Service enabled"
}

disable_service() {
    echo "Disabling RStudio cleanup service..."
    sudo systemctl disable $TIMER_NAME
    sudo systemctl disable $SERVICE_NAME
    echo "✅ Service disabled"
}

install_daemon() {
    check_root
    echo "Installing RStudio cleanup daemon..."

    # Run the setup script
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/setup_daemon.sh" ]; then
        bash "$SCRIPT_DIR/setup_daemon.sh"
    else
        echo "Error: setup_daemon.sh not found in $SCRIPT_DIR"
        exit 1
    fi
}

uninstall_daemon() {
    check_root
    echo "Uninstalling RStudio cleanup daemon..."

    # Stop and disable services
    systemctl stop $TIMER_NAME 2>/dev/null || true
    systemctl disable $TIMER_NAME 2>/dev/null || true
    systemctl disable $SERVICE_NAME 2>/dev/null || true

    # Remove service files
    rm -f /etc/systemd/system/$SERVICE_NAME.service
    rm -f /etc/systemd/system/$TIMER_NAME

    # Reload systemd
    systemctl daemon-reload

    echo "✅ Daemon uninstalled"
    echo "Note: Application files and logs are preserved"
}

test_cleanup() {
    echo "Running cleanup manually..."
    sudo systemctl start $SERVICE_NAME
    echo "✅ Manual cleanup completed. Check logs for details."
}

case "${1:-}" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    enable)
        enable_service
        ;;
    disable)
        disable_service
        ;;
    install)
        install_daemon
        ;;
    uninstall)
        uninstall_daemon
        ;;
    test)
        test_cleanup
        ;;
    *)
        usage
        ;;
esac
