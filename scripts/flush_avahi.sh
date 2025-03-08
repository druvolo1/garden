#!/bin/bash
# flush_avahi.sh
# Stop Avahi, remove stale runtime files, then restart Avahi fresh.

set -e  # Exit if any command fails

echo "Stopping avahi-daemon..."
sudo systemctl stop avahi-daemon

# Remove Avahi's PID/socket files from /var/run (runtime directory).
# Typically, these are safe to remove once Avahi is stopped.
# Adjust paths as needed if your distro differs.
echo "Removing Avahi runtime files..."
sudo rm -f /var/run/avahi-daemon/pid
sudo rm -f /var/run/avahi-daemon/socket

# If you want to be extra sure, or if your distro stores some state in /var/lib/avahi,
# you might also remove entries there. But usually /var/run is enough to clear stale records.

echo "Starting avahi-daemon..."
sudo systemctl start avahi-daemon

echo "Avahi has been restarted and old records flushed."
