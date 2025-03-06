#!/bin/bash
#setup_updater.sh

set -e

# 1) Copy the systemd unit to the correct location
sudo cp /home/dave/garden/scripts/garden-updater.service /etc/systemd/system/

# 2) Reload systemd
sudo systemctl daemon-reload

# 3) Optional: enable so it can be started at any time
sudo systemctl enable garden-updater.service

# 4) Make sure the script is executable
sudo chmod +x /home/dave/garden/scripts/garden_update.sh
