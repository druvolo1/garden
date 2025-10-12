# File: api/update_code.py

import os
import shlex
import subprocess
import stat
from flask import Blueprint, jsonify

update_code_blueprint = Blueprint("update_code", __name__)

# Dynamically determine the project root (assuming this file is in api/update_code.py)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Path to your script INSIDE the project:
# e.g. scripts/garden_update.sh relative to PROJECT_ROOT
SCRIPT_PATH = os.path.join(PROJECT_ROOT, "scripts", "garden_update.sh")

# Path to venv and venv pip
VENV_PATH = os.path.join(PROJECT_ROOT, "venv")
VENV_PIP = os.path.join(VENV_PATH, "bin", "pip")


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


def ensure_venv_ownership(venv_path: str, user_group: str = "dave:dave"):
    """
    Check if the venv is owned by the specified user:group; if not, run sudo chown -R.
    This avoids unnecessary sudo calls.
    """
    # Get current owner/group
    stat_info = os.stat(venv_path)
    current_uid = stat_info.st_uid
    current_gid = stat_info.st_gid

    # Get target user/group IDs (from current user for simplicity, or hardcoded)
    import pwd
    import grp
    target_user = user_group.split(":")[0]
    target_group = user_group.split(":")[1]
    target_uid = pwd.getpwnam(target_user).pw_uid
    target_gid = grp.getgrnam(target_group).gr_gid

    if current_uid != target_uid or current_gid != target_gid:
        print(f"[INFO] Fixing venv ownership: sudo chown -R {user_group} {venv_path}")
        out, err = run_cmd(["sudo", "chown", "-R", user_group, venv_path])
        if err:
            raise RuntimeError(f"Failed to chown venv: {err}")
        return out
    else:
        print("[INFO] Venv ownership is correct; skipping chown.")
        return None


def _check_for_update():
    """
    Helper to check for updates (extracted logic).
    Returns (update_available: bool, message: str, error: str or None)
    """
    try:
        # Git fetch to update remote refs
        fetch_proc = subprocess.run(['git', 'fetch'], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30)
        if fetch_proc.returncode != 0:
            return False, "Failed to fetch updates", "Failed to fetch updates"

        # Check status
        status_proc = subprocess.run(['git', 'status', '-uno'], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30)
        git_status = status_proc.stdout.strip()
        if 'Your branch is behind' in git_status:
            return True, "Update available", None
        else:
            return False, "No update available", None
    except subprocess.TimeoutExpired:
        return False, "Check timed out", "Check timed out"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}", str(e)


def _apply_update():
    """
    Helper to apply updates (extracted logic).
    Returns (success: bool, output: str, error: str or None)
    """
    steps_output = []
    try:
        # 1) Hard reset: discards all local changes before pulling
        out, err = run_cmd(["git", "reset", "--hard"], cwd=PROJECT_ROOT)
        steps_output.append(out)
        if err:
            return False, "\n".join(steps_output), err

        # 2) Pull latest changes (continue even if fails)
        out, err = run_cmd(["git", "pull"], cwd=PROJECT_ROOT)
        steps_output.append(out)
        if err:
            return False, "\n".join(steps_output), err

        # 3) Ensure venv ownership before pip install
        chown_out = ensure_venv_ownership(VENV_PATH)
        if chown_out:
            steps_output.append(chown_out)

        # 4) Install any new requirements
        req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
        out, err = run_cmd(
            ["sudo", VENV_PIP, "install", "-r", req_path],
            cwd=PROJECT_ROOT
        )
        steps_output.append(out)
        if err:
            return False, "\n".join(steps_output), err

        # Restart the service
        subprocess.Popen(['sudo', 'systemctl', 'restart', 'garden.service'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=PROJECT_ROOT)

        return True, "\n".join(steps_output), None
    except subprocess.TimeoutExpired:
        return False, "\n".join(steps_output), "Update timed out"
    except Exception as e:
        return False, "\n".join(steps_output), f"Unexpected error: {str(e)}"


@update_code_blueprint.route("/check_update", methods=["GET"])
def check_update():
    update_available, message, error = _check_for_update()
    if error:
        return jsonify({"status": "failure", "error": error}), 500
    return jsonify({"status": "success", "update_available": update_available, "message": message})


@update_code_blueprint.route("/apply_update", methods=["POST"])
def apply_update():
    success, output, error = _apply_update()
    if error:
        return jsonify({"status": "failure", "error": error, "output": output}), 500
    return jsonify({"status": "success", "output": output})


@update_code_blueprint.route("/auto_update", methods=["POST"])
def auto_update():
    """
    Single endpoint: Check for update, and if available, apply it.
    """
    steps_output = []
    update_available, check_message, check_error = _check_for_update()
    steps_output.append(check_message)
    if check_error:
        return jsonify({"status": "failure", "error": check_error, "output": "\n".join(steps_output)}), 500

    if not update_available:
        return jsonify({"status": "success", "message": "No update available, nothing applied", "output": "\n".join(steps_output)})

    # Apply if available
    success, apply_output, apply_error = _apply_update()
    steps_output.append(apply_output)
    if apply_error:
        return jsonify({"status": "failure", "error": apply_error, "output": "\n".join(steps_output)}), 500

    return jsonify({"status": "success", "message": "Update checked and applied", "output": "\n".join(steps_output)})


@update_code_blueprint.route("/pull_no_restart", methods=["POST"])
def pull_no_restart():
    """
    1) git reset --hard
    2) git pull
    3) chown venv (if needed)
    4) pip install -r requirements.txt
    (No service restart)
    Continues to install requirements even if git pull fails.
    """
    steps_output = []
    errors = []
    try:
        # 1) Hard reset: discards all local changes before pulling
        out, err = run_cmd(["git", "reset", "--hard"], cwd=PROJECT_ROOT)
        steps_output.append(out)
        if err:
            errors.append(err)

        # 2) Pull latest changes (continue even if fails)
        out, err = run_cmd(["git", "pull"], cwd=PROJECT_ROOT)
        steps_output.append(out)
        if err:
            errors.append(err)

        # 3) Ensure venv ownership before pip install
        chown_out = ensure_venv_ownership(VENV_PATH)
        if chown_out:
            steps_output.append(chown_out)

        # 4) Install any new requirements
        req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
        out, err = run_cmd(
            ["sudo", VENV_PIP, "install", "-r", req_path],
            cwd=PROJECT_ROOT
        )
        steps_output.append(out)
        if err:
            errors.append(err)

        combined_error = "\n".join(errors) if errors else None
        if combined_error:
            return jsonify({
                "status": "failure",
                "error": combined_error,
                "output": "\n".join(steps_output)
            }), 500
        else:
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