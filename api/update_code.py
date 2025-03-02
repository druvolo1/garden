# File: api/update_code.py

import subprocess
import os
import shlex
from flask import Blueprint, jsonify

update_code_blueprint = Blueprint('update_code', __name__)

# Adjust paths/names to match your environment
TARGET_DIR   = "/home/dave/garden"              # Where to clone the repo
GIT_URL      = "https://github.com/druvolo1/garden.git"
SERVICE_NAME = "garden.service"                 # The systemd service to restart
PIP_COMMAND  = "pip"                            # Or an absolute path, e.g. "/home/dave/garden/venv/bin/pip"

def run_cmd(cmd_list, cwd=None):
    """
    Helper to run a shell command, capturing output.
    Returns (success_output_str, None) if success, or (partial_output_str, error_str) if error.
    """
    cmd_str = " ".join(shlex.quote(str(x)) for x in cmd_list)
    logs = [f"Running: {cmd_str}"]
    try:
        out = subprocess.check_output(cmd_list, stderr=subprocess.STDOUT, cwd=cwd)
        logs.append(out.decode('utf-8', errors='replace'))
        return ("\n".join(logs), None)  # success, no error
    except subprocess.CalledProcessError as e:
        logs.append(e.output.decode('utf-8', errors='replace'))
        err_str = f"Command failed with exit code {e.returncode}"
        return ("\n".join(logs), err_str)
    except Exception as ex:
        err_str = f"Unexpected exception: {str(ex)}"
        logs.append(err_str)
        return ("\n".join(logs), err_str)


@update_code_blueprint.route('/pull', methods=['POST'])
def pull_and_restart():
    """
    1) Remove the old 'garden' directory for a fresh clone
    2) Clone the Git repo into TARGET_DIR
    3) pip install -r requirements.txt
    4) systemctl restart garden.service
    Returns JSON logs of each step.
    """
    steps_output = []
    try:
        # 1) Remove existing folder (fresh start)
        if os.path.exists(TARGET_DIR):
            out, err = run_cmd(["rm", "-rf", TARGET_DIR])
            steps_output.append(out)
            if err:
                return jsonify({
                    "status":"failure","error":err,
                    "output":"\n".join(steps_output)
                }), 500

        # 2) Clone the repo
        out, err = run_cmd(["git", "clone", GIT_URL, TARGET_DIR])
        steps_output.append(out)
        if err:
            return jsonify({
                "status":"failure","error":err,
                "output":"\n".join(steps_output)
            }), 500

        # 3) pip install -r requirements.txt
        out, err = run_cmd([PIP_COMMAND, "install", "-r", "requirements.txt"], cwd=TARGET_DIR)
        steps_output.append(out)
        if err:
            return jsonify({
                "status":"failure","error":err,
                "output":"\n".join(steps_output)
            }), 500

        # 4) Restart the systemd service
        out, err = run_cmd(["sudo", "systemctl", "restart", SERVICE_NAME])
        steps_output.append(out)
        if err:
            return jsonify({
                "status":"failure","error":err,
                "output":"\n".join(steps_output)
            }), 500

        # If everything succeeded
        return jsonify({
            "status": "success",
            "output": "\n".join(steps_output)
        })

    except Exception as ex:
        steps_output.append(str(ex))
        return jsonify({
            "status":"failure",
            "error": str(ex),
            "output":"\n".join(steps_output)
        }), 500
