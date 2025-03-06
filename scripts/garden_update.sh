#!/bin/bash
# garden_update.sh
# This script pulls the latest code & dependencies, then restarts garden.service.
# Using "restart" means the app only goes offline briefly at the very end.

# We'll store logs here:
LOGFILE="/var/log/garden_update.log"

# Redirect all script output (stdout & stderr) to both the console and the log file.
# This means everything echoes as usual, and also goes to /var/log/garden_update.log.
exec > >(tee -a "$LOGFILE") 2>&1

cd /home/dave/garden
source venv/bin/activate

echo "[$(date)] Pulling latest code..."
git pull

echo "[$(date)] Installing dependencies..."
pip install -r requirements.txt

echo "[$(date)] Restarting garden.service..."
sudo systemctl restart garden.service

echo "[$(date)] Update script finished successfully."
