#!/bin/bash
# garden_update.sh

# Pull latest code
cd /home/dave/garden
git pull

# Source venv and update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Finally, restart the service in one step
sudo systemctl restart garden.service
