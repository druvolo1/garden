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
        logs.append(out.decode("utf-8", errors="replace"))
        return ("\n".join(logs), None)  # success, no error
    except subprocess.CalledProcessError as e:
        logs.append(e.output.decode("utf-8", errors="replace"))
        err_str = f"Command failed with exit code {e.returncode}"
        return ("\n".join(logs), err_str)
    except Exception as ex:
        err_str = f"Unexpected exception: {str(ex)}"
        logs.append(err_str)
        return ("\n".join(logs), err_str)


@update_code_blueprint.route("/pull", methods=["POST"])
def pull_and_restart():
    """
    Calls the garden_update.sh script located in /home/dave/garden/scripts/.
    That script is responsible for:
      1) Stopping garden.service
      2) Git pulling the latest code
      3) Installing requirements
      4) Starting garden.service

    Returns JSON logs from the script.
    """
    steps_output = []

    # Just call the script in one go:
    out, err = run_cmd(["/bin/bash", SCRIPT_PATH])

    steps_output.append(out)
    if err:
        return jsonify({
            "status": "failure",
            "error": err,
            "output": "\n".join(steps_output)
        }), 500

    # success
    return jsonify({
        "status": "success",
        "output": "\n".join(steps_output)
    })
