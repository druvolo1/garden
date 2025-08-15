#!/bin/bash
# garden_update.sh
# This script pulls the latest code & dependencies, then restarts garden.service.
# Using "restart" means the app only goes offline briefly at the very end.

# Figure out which directory this script resides in:
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# We'll store logs in the same folder:
LOGFILE="${SCRIPTDIR}/garden_update.log"

# Redirect all script output (stdout & stderr) to both the console and the log file.
exec > >(tee -a "$LOGFILE") 2>&1

cd /home/dave/garden

echo "[$(date)] Fixing venv permissions..."
sudo chown -R $(whoami):$(whoami) venv

source venv/bin/activate

echo "[$(date)] Pulling latest code..."
git pull

echo "[$(date)] Installing dependencies..."
pip install -r requirements.txt

echo "[$(date)] Restarting garden.service..."
sudo systemctl restart garden.service

echo "[$(date)] Update script finished successfully."