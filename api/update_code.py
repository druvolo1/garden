# File: api/update_code.py

import os
import shlex
import subprocess
import stat
from flask import Blueprint, jsonify

update_code_blueprint = Blueprint("update_code", __name__)

# Path to your script INSIDE the garden project:
# e.g. /home/dave/garden/scripts/garden_update.sh
SCRIPT_PATH = "/home/dave/garden/scripts/garden_update.sh"


def ensure_script_executable(script_path: str):
    """
    Check if script is executable by the owner; if not, chmod +x.
    """
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")
    mode = os.stat(script_path).st_mode
    # Check if "owner execute" bit is set:
    if not (mode & stat.S_IXUSR):
        print(f"[INFO] Making {script_path} executable (chmod +x)")
        subprocess.run(["chmod", "+x", script_path], check=True)


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
            if "Requirement already satisfied" in line:
                continue
            if "Already up to date" in line:
                continue
            filtered_lines.append(line)

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
    1) git reset --hard
    2) git pull
    3) pip install -r requirements.txt
    (No service restart)
    """
    steps_output = []
    try:
        # 1) Hard reset: discards all local changes before pulling
        out, err = run_cmd(["git", "reset", "--hard"], cwd="/home/dave/garden")
        steps_output.append(out)
        if err:
            return jsonify({
                "status": "failure",
                "error": err,
                "output": "\n".join(steps_output)
            }), 500

        # 2) Pull latest changes
        out, err = run_cmd(["git", "pull"], cwd="/home/dave/garden")
        steps_output.append(out)
        if err:
            return jsonify({
                "status": "failure",
                "error": err,
                "output": "\n".join(steps_output)
            }), 500

        # 3) Install any new requirements
        out, err = run_cmd(
            ["/home/dave/garden/venv/bin/pip", "install", "-r", "requirements.txt"],
            cwd="/home/dave/garden"
        )
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


@update_code_blueprint.route("/garden_update", methods=["POST"])
def run_garden_update_script():
    """
    Example route that calls garden_update.sh for your custom update logic.
    """
    steps_output = []
    try:
        # Ensure the script is present & executable
        ensure_script_executable(SCRIPT_PATH)

        # Now run the script via sudo
        out, err = run_cmd(["sudo", SCRIPT_PATH])
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
