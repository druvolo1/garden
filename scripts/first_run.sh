#!/usr/bin/env python3
import os
import subprocess
import sys

SERVICE_PATH = "/etc/systemd/system/garden.service"

SERVICE_CONTENT = """[Unit]
Description=pH Gunicorn Service
After=network.target

[Service]
# Adjust 'User=' to whichever user should own/run the garden process
User=dave
WorkingDirectory=/home/dave/garden

# Use bash so we can 'source' the venv
ExecStart=/bin/bash -c 'cd /home/dave/garden && source venv/bin/activate && gunicorn --config gunicorn_config.py -w 1 -k eventlet wsgi:app --bind 0.0.0.0:8000 --log-level=debug'

# Automatically restart if it crashes
Restart=always

[Install]
WantedBy=multi-user.target
"""

def run_command(cmd_list, description=None):
    """
    Helper to run shell commands with a descriptive message.
    Raises an exception if the command fails.
    """
    if description:
        print(f"\n=== {description} ===")
    print("Running:", " ".join(cmd_list))
    subprocess.run(cmd_list, check=True)

def main():
    # 1) Must run as root
    if os.geteuid() != 0:
        print("Please run this script with sudo or as root.")
        sys.exit(1)

    # 2) Update & upgrade
    run_command(["apt-get", "update"], "apt-get update")
    run_command(["apt-get", "upgrade", "-y"], "apt-get upgrade")

    # 3) Install needed packages
    run_command(["apt-get", "install", "-y", "git", "python3", "python3-venv", "python3-pip"],
                "Install Git, Python 3, venv, pip")

    # Note: We are NOT cloning the repo here,
    # because you indicated you already did a git pull.

    # 4) Create & activate a virtual environment
    if not os.path.isdir("/home/dave/garden/venv"):
        print("\n=== Creating virtual environment as user dave ===")
        run_command(["sudo", "-u", "dave", "python3", "-m", "venv", "/home/dave/garden/venv"],
                    "Create Python venv in /home/dave/garden/venv")
    else:
        print("\n=== venv already exists. Skipping creation. ===")

    # 5) Upgrade pip & install requirements (run as dave)
    run_command(["sudo", "-u", "dave", "/home/dave/garden/venv/bin/pip", "install", "--upgrade", "pip"],
                "Upgrade pip in the venv")

requirements_file = "/home/dave/garden/requirements.txt"
if os.path.isfile(requirements_file):
    run_command(["sudo", "-u", "dave", "/home/dave/garden/venv/bin/pip", "install", "-r", requirements_file],
                "Install Python dependencies from requirements.txt")
else:
    print(f"\n=== {requirements_file} not found! Skipping pip install -r. ===")

    requirements_file = "/home/dave/garden/requirements.txt"
    if os.path.isfile(requirements_file):
        run_command(["/home/dave/garden/venv/bin/pip", "install", "-r", requirements_file],
                    "Install Python dependencies from requirements.txt")
    else:
        print(f"\n=== {requirements_file} not found! Skipping pip install -r. ===")

    # 6) Create the systemd service file
    print(f"\n=== Creating systemd service at {SERVICE_PATH} ===")
    with open(SERVICE_PATH, "w") as f:
        f.write(SERVICE_CONTENT)

    # 7) Reload systemd so it sees the new service
    run_command(["systemctl", "daemon-reload"], "Reload systemd")

    # 8) Enable and start the garden service
    run_command(["systemctl", "enable", "garden.service"], "Enable garden.service on startup")
    run_command(["systemctl", "start", "garden.service"], "Start garden.service now")

    print("\n=== Setup complete! ===")
    print("You can check logs with:  journalctl -u garden.service -f")
    print("You can check status with: systemctl status garden.service")


if __name__ == "__main__":
    main()
