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
def launch_updater_service():
    """
    Runs garden-updater.service, which in turn calls garden_update.sh.
    """
    try:
        # Just systemctl start the new service
        output = subprocess.check_output(
            ["sudo", "systemctl", "start", "garden-updater.service"],
            stderr=subprocess.STDOUT
        )
        return jsonify({
            "status": "success",
            "output": output.decode("utf-8", errors="replace")
        })
    except subprocess.CalledProcessError as e:
        return jsonify({
            "status": "failure",
            "error": f"Command failed with exit code {e.returncode}",
            "output": e.output.decode("utf-8", errors="replace")
        }), 500
    except Exception as ex:
        return jsonify({
            "status": "failure",
            "error": str(ex)
        }), 500

