#!/bin/bash
# garden_update.sh
# This script pulls the latest code & dependencies, then restarts garden.service.
# Using "restart" means the app only goes offline briefly at the very end.

# Figure out which directory this script resides in (assumes script is in the garden dir):
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# We'll store logs in the same folder:
LOGFILE="${SCRIPTDIR}/garden_update.log"

# Redirect all script output (stdout & stderr) to both the console and the log file.
exec > >(tee -a "$LOGFILE") 2>&1

# Dynamically detect the current user and group (assumes script run as app user)
APP_USER=$(whoami)
APP_GROUP=$(id -gn "$APP_USER")

# Set garden dir to where the script is
GARDEN_DIR="$SCRIPTDIR"
cd "$GARDEN_DIR" || { echo "[$(date)] Failed to cd to $GARDEN_DIR"; exit 1; }

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "[$(date)] venv directory not found. Creating it..."
    python3 -m venv venv || { echo "[$(date)] Failed to create venv"; exit 1; }
fi

# Fix venv permissions if needed (conditional: only if not already owned by app user)
if [ "$(stat -c '%U' venv)" != "$APP_USER" ]; then
    echo "[$(date)] Fixing venv permissions..."
    sudo chown -R "$APP_USER:$APP_GROUP" venv || { echo "[$(date)] Failed to chown venv"; exit 1; }
fi

# Activate venv
source venv/bin/activate || { echo "[$(date)] Failed to activate venv"; exit 1; }

echo "[$(date)] Upgrading pip for reliability..."
pip install --upgrade pip || { echo "[$(date)] Failed to upgrade pip"; exit 1; }

echo "[$(date)] Pulling latest code..."
git pull || { echo "[$(date)] Git pull failed"; exit 1; }

echo "[$(date)] Installing dependencies..."
pip install -r requirements.txt --no-cache-dir || { echo "[$(date)] Pip install failed"; exit 1; }

echo "[$(date)] Restarting garden.service..."
sudo systemctl restart garden.service || { echo "[$(date)] Service restart failed"; exit 1; }

echo "[$(date)] Update script finished successfully."