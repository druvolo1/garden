# File: api/update_code.py

import os
import shlex
import subprocess
from flask import Blueprint, jsonify

update_code_blueprint = Blueprint("update_code", __name__)

# Adjust these to your environment:
TARGET_DIR   = "/home/dave/garden"   # Path where your repo lives
GIT_URL      = "https://github.com/druvolo1/garden.git"
SERVICE_NAME = "garden.service"      # systemd service to restart
PIP_COMMAND  = "pip"                 # Could be "/home/dave/garden/venv/bin/pip" if using a venv

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
    1) If TARGET_DIR is a Git repo -> run 'git pull'. If it reports 'Already up to date.',
       we skip the pip install and systemctl restart (nothing changed).
       Otherwise -> proceed with pip install & restart.
       If TARGET_DIR is not a Git repo -> 'git clone' into TARGET_DIR.
    2) pip install -r requirements.txt
    3) systemctl restart SERVICE_NAME
    Returns JSON logs of each step.
    """
    steps_output = []
    try:
        # 1) Check if we already have a Git repo
        if os.path.isdir(TARGET_DIR) and os.path.isdir(os.path.join(TARGET_DIR, ".git")):
            # We have an existing repo => do git pull
            out, err = run_cmd(["git", "pull"], cwd=TARGET_DIR)
            steps_output.append(out)

            if err:
                return jsonify({
                    "status": "failure",
                    "error": err,
                    "output": "\n".join(steps_output)
                }), 500

            # If we see "Already up to date." in the git output, just exit cleanly
            if "Already up to date." in out:
                return jsonify({
                    "status": "success",
                    "output": "No new commits. Already up to date.\nNothing else to do."
                })
        else:
            # No .git => clone fresh
            parent_dir = os.path.dirname(TARGET_DIR)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir)

            out, err = run_cmd(["git", "clone", GIT_URL, TARGET_DIR])
            steps_output.append(out)
            if err:
                return jsonify({
                    "status": "failure",
                    "error": err,
                    "output": "\n".join(steps_output)
                }), 500

        # 2) pip install -r requirements.txt
        out, err = run_cmd([PIP_COMMAND, "install", "-r", "requirements.txt"], cwd=TARGET_DIR)
        steps_output.append(out)
        if err:
            return jsonify({
                "status": "failure",
                "error": err,
                "output": "\n".join(steps_output)
            }), 500

        # 3) systemctl restart
        out, err = run_cmd(["sudo", "systemctl", "restart", SERVICE_NAME])
        steps_output.append(out)
        if err:
            return jsonify({
                "status": "failure",
                "error": err,
                "output": "\n".join(steps_output)
            }), 500

        # If we got here, everything succeeded
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
