# File: api/update_code.py

import subprocess
import os
from flask import Blueprint, jsonify

update_code_blueprint = Blueprint('update_code', __name__)

# Point this to the local path of your cloned git repository:
REPO_DIR = "/home/pi/garden"  # Example. Adjust to match your actual git folder.

@update_code_blueprint.route('/pull', methods=['POST'])
def pull_and_restart():
    """
    1. Perform git pull in REPO_DIR
    2. If successful, restart the 'garden.service' via systemd
    3. Return JSON response with any output or errors
    """
    try:
        # Step 1: Pull the latest code
        pull_output = subprocess.check_output(
            ["git", "pull"],
            cwd=REPO_DIR,
            stderr=subprocess.STDOUT
        )

        # Step 2: Restart your systemd service (e.g. garden.service)
        # Make sure garden.service actually exists & you have passwordless sudo
        restart_output = subprocess.check_output(
            ["sudo", "systemctl", "restart", "garden.service"],
            stderr=subprocess.STDOUT
        )

        # If we got here, both steps succeeded
        return jsonify({
            "status": "success",
            "pull_output": pull_output.decode("utf-8"),
            "restart_output": restart_output.decode("utf-8")
        })

    except subprocess.CalledProcessError as e:
        # For Git or systemctl errors
        return jsonify({
            "status": "failure",
            "error": str(e),
            "output": e.output.decode("utf-8") if e.output else "No output"
        }), 500

    except Exception as e:
        # Catch any other unexpected exceptions
        return jsonify({"status": "failure", "error": str(e)}), 500
