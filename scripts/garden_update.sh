#!/bin/bash
# garden_update.sh
# This script pulls the latest code & dependencies, then restarts garden.service.
# Using "restart" means the app only goes offline briefly at the very end.

cd /home/dave/garden
source venv/bin/activate

echo "Pulling latest code..."
git pull

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Restarting garden.service..."
sudo systemctl restart garden.service
