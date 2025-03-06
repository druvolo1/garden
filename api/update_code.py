# File: api/update_code.py

import os
import shlex
import subprocess
from flask import Blueprint, jsonify

update_code_blueprint = Blueprint("update_code", __name__)

# Path to your script INSIDE the garden project:
# e.g. /home/dave/garden/scripts/garden_update.sh
SCRIPT_PATH = "/home/dave/garden/scripts/garden_update.sh"


def run_cmd(cmd_list, cwd=None):
    """
    Helper to run a shell command and capture output.
    Returns (output_str, None) if success, or (output_str, err_str) if error.
    """
    cmd_str = " ".join(shlex.quote(str(x)) for x in cmd_list)
    logs = [f"Running: {cmd_str}"]
    try:
        out = subprocess.check_output(cmd_list, stderr=subprocess.STDOUT, cwd=cwd)
        decoded = out.decode("utf-8", errors="replace")

        # Filter out lines you consider "noise"
        lines = decoded.splitlines()
        filtered_lines = []
        for line in lines:
            # Example: skip "already satisfied" or "Already up to date"
            if "Requirement already satisfied" in line:
                continue
            if "Already up to date" in line:
                continue
            filtered_lines.append(line)

        # Rebuild the string from filtered lines
        filtered_out = "\n".join(filtered_lines)
        logs.append(filtered_out)

        return ("\n".join(logs), None)  # success, no error

    except subprocess.CalledProcessError as e:
        logs.append(e.output.decode("utf-8", errors="replace"))
        err_str = f"Command failed with exit code {e.returncode}"
        return ("\n".join(logs), err_str)

    except Exception as ex:
        err_str = f"Unexpected exception: {str(ex)}"
        logs.append(err_str)
        return ("\n".join(logs), err_str)


@update_code_blueprint.route("/pull_no_restart", methods=["POST"])
def pull_no_restart():
    """
    1) git pull
    2) pip install -r requirements.txt
    (No service restart)
    """
    steps_output = []
    try:
        # run_cmd is your existing helper that does subprocess.check_output
        out, err = run_cmd(["git", "pull"], cwd="/home/dave/garden")
        steps_output.append(out)
        if err:
            return jsonify({
                "status": "failure",
                "error": err,
                "output": "\n".join(steps_output)
            }), 500

        out, err = run_cmd(["/home/dave/garden/venv/bin/pip", "install", "-r", "requirements.txt"],
                           cwd="/home/dave/garden")
        steps_output.append(out)
        if err:
            return jsonify({
                "status": "failure",
                "error": err,
                "output": "\n".join(steps_output)
            }), 500

        return jsonify({
            "status": "success",
            "output": "\n".join(steps_output)
        })
    except Exception as ex:
        steps_output.append(str(ex))
        return jsonify({
            "status": "failure",
            "error": str(ex),
            "output": "\n".join(steps_output)
        }), 500

@update_code_blueprint.route("/restart", methods=["POST"])
def restart_service():
    """
    Just restarts garden.service
    """
    steps_output = []
    try:
        out, err = run_cmd(["sudo", "systemctl", "restart", "garden.service"])
        steps_output.append(out)
        if err:
            return jsonify({
                "status": "failure",
                "error": err,
                "output": "\n".join(steps_output)
            }), 500

        return jsonify({
            "status": "success",
            "output": "\n".join(steps_output)
        })
    except Exception as ex:
        steps_output.append(str(ex))
        return jsonify({
            "status": "failure",
            "error": str(ex),
            "output": "\n".join(steps_output)
        }), 500
