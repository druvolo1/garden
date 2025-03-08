#!/bin/bash
# setup_updater.sh

set -e

# Figure out which directory this script resides in:
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOGFILE="${SCRIPTDIR}/setup_updater.log"

# Redirect all script output to both console and log file in the same dir
exec > >(tee -a "$LOGFILE") 2>&1

echo "[$(date)] Starting setup_updater.sh..."

# 1) Copy the systemd unit to the correct location
echo "[$(date)] Copying garden-updater.service to /etc/systemd/system/"
sudo cp /home/dave/garden/scripts/garden-updater.service /etc/systemd/system/

# 2) Reload systemd
echo "[$(date)] Reloading systemd daemon..."
sudo systemctl daemon-reload

# 3) Optional: enable so it can be started at any time
echo "[$(date)] Enabling garden-updater.service..."
sudo systemctl enable garden-updater.service

# 4) Make sure the script is executable
echo "[$(date)] Ensuring garden_update.sh is executable..."
sudo chmod +x /home/dave/garden/scripts/garden_update.sh

# 5) Make sure the script is executable
echo "[$(date)] Ensuring change_hostname.sh is executable..."
sudo chmod +x /home/dave/garden/scripts/change_hostname.sh

echo "[$(date)] setup_updater.sh completed."
