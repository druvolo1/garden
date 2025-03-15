#!/usr/bin/env python3

import os
import subprocess

SERVICE_PATH = "/etc/systemd/system/garden.service"

SERVICE_CONTENT = """[Unit]
Description=Garden Gunicorn Service
After=network.target

[Service]
# Adjust 'User=' to whichever user owns /home/dave/garden if needed
User=dave
WorkingDirectory=/home/dave/garden

# The ExecStart runs your commands to activate venv + run gunicorn
ExecStart=/bin/bash -c 'cd /home/dave/garden && source venv/bin/activate && clear && gunicorn -w 1 -k eventlet wsgi:app --bind 0.0.0.0:8000 --log-level=debug'

# Restart automatically if the process crashes
Restart=always

[Install]
WantedBy=multi-user.target
"""

def main():
    # 1) Write the service file
    print(f"Creating {SERVICE_PATH} ...")
    with open(SERVICE_PATH, "w") as f:
        f.write(SERVICE_CONTENT)

    # 2) Reload systemd so it sees the new service file
    subprocess.run(["systemctl", "daemon-reload"], check=True)

    # 3) Enable the service on boot
    subprocess.run(["systemctl", "enable", "garden.service"], check=True)

    # 4) Start the service right now
    subprocess.run(["systemctl", "start", "garden.service"], check=True)

    print("garden.service created, enabled, and started successfully!")

if __name__ == "__main__":
    # Typically, you need to run this script with sudo or root privileges
    # so it can write /etc/systemd/system/garden.service
    if os.geteuid() != 0:
        print("Please run as root (e.g. sudo python create_garden_service.py)")
        exit(1)
    main()
