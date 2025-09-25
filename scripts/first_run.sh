#!/usr/bin/env python3
import os
import subprocess
import sys

SERVICE_PATH = "/etc/systemd/system/garden.service"

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

    # Get the original user who ran sudo
    user = os.environ['SUDO_USER']
    home_dir = f"/home/{user}"
    garden_dir = f"{home_dir}/garden"
    venv_dir = f"{garden_dir}/venv"
    requirements_file = f"{garden_dir}/requirements.txt"

    SERVICE_CONTENT = f"""[Unit]
Description=pH Gunicorn Service
After=network.target

[Service]
# Adjust 'User=' to whichever user should own/run the garden process
User={user}
WorkingDirectory={garden_dir}

# Use bash so we can 'source' the venv
ExecStart=/bin/bash -c 'cd {garden_dir} && source venv/bin/activate && gunicorn -w 1 -k eventlet wsgi:app --bind 0.0.0.0:8000 --log-level=debug'

# Automatically restart if it crashes
Restart=always

[Install]
WantedBy=multi-user.target
"""

    # 2) Update & upgrade
    run_command(["apt-get", "update"], "apt-get update")
    run_command(["apt-get", "upgrade", "-y"], "apt-get upgrade")

    # 3) Install needed packages
    run_command(["apt-get", "install", "-y", "git", "python3", "python3-venv", "python3-pip", "avahi-utils"],
                "Install Git, Python 3, venv, pip, and avahi-utils for mDNS")

    # Note: We are NOT cloning the repo here,
    # because you indicated you already did a git pull.

    # 4) Create & activate a virtual environment
    if not os.path.isdir(venv_dir):
        print(f"\n=== Creating virtual environment as user {user} ===")
        run_command(["sudo", "-u", user, "python3", "-m", "venv", venv_dir],
                    f"Create Python venv in {venv_dir}")
    else:
        print("\n=== venv already exists. Skipping creation. ===")

    # 5) Upgrade pip & install requirements (run as user)
    run_command(["sudo", "-u", user, f"{venv_dir}/bin/pip", "install", "--upgrade", "pip"],
                "Upgrade pip in the venv")

    if os.path.isfile(requirements_file):
        run_command(["sudo", "-u", user, f"{venv_dir}/bin/pip", "install", "-r", requirements_file],
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