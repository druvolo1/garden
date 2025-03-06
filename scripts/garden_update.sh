#!/bin/bash

# garden_update.sh
# This script will stop garden, pull latest code, install deps, then restart.

sudo systemctl stop garden.service
cd /home/dave/garden
source venv/bin/activate
git pull
pip install -r requirements.txt
sudo systemctl start garden.service
