# File: api/logs.py

from flask import Blueprint, jsonify, request, send_file
import os
import json
from datetime import datetime

# Create the Blueprint for logs
log_blueprint = Blueprint('logs', __name__)

# Path to the logs directory (updated for consistency with multi-file support)
LOG_DIR = os.path.join(os.getcwd(), "data", "logs")
# Example single-file path (kept for backward compatibility if needed, but now we support multiple files)
LOGS_FILE = os.path.join(LOG_DIR, "sensor_log.jsonl")

# Ensure the logs directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Ensure an example logs file exists (empty if not) – optional, as we now list all files
if not os.path.exists(LOGS_FILE):
    open(LOGS_FILE, "w").close()


# Helper function: Load logs from JSONL file, filtering for dosing events (kept for / endpoint)
def load_logs():
    logs = []
    if os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if entry.get("event_type") == "dosing":  # Filter to dosing only for this API
                            logs.append(entry)
                    except json.JSONDecodeError:
                        pass  # Skip malformed lines
    return logs


# API Endpoint: Get all dosing logs (from the primary JSONL file – kept for compatibility)
@log_blueprint.route('/', methods=['GET'])
def get_logs():
    """
    Retrieve all dosage logs (filtered from the primary JSONL file).
    """
    logs = load_logs()
    return jsonify(logs)


# API Endpoint: Clear all logs (truncate the primary file – kept for compatibility; consider updating to clear all files if needed)
@log_blueprint.route('/clear', methods=['POST'])
def clear_logs():
    """
    Clear all logs by truncating the primary file.
    """
    open(LOGS_FILE, "w").close()
    return jsonify({"status": "success", "message": "Logs cleared."})


# NEW: API Endpoint: List all log files in the directory
@log_blueprint.route('/list', methods=['GET'])
def list_logs():
    """
    List all files in the logs directory.
    """
    try:
        files = [f for f in os.listdir(LOG_DIR) if os.path.isfile(os.path.join(LOG_DIR, f))]
        return jsonify(files)
    except Exception as e:
        return jsonify({"status": "failure", "message": str(e)}), 500


# NEW: API Endpoint: View the content of a specific log file (as plain text)
@log_blueprint.route('/view/<path:file>', methods=['GET'])
def view_log(file):
    """
    View the content of a specific log file.
    """
    log_path = os.path.join(LOG_DIR, file)
    if not os.path.exists(log_path):
        return jsonify({"status": "failure", "message": "File not found"}), 404
    with open(log_path, 'r') as f:
        content = f.read()
    return content, 200, {'Content-Type': 'text/plain'}


# NEW: API Endpoint: Download a specific log file
@log_blueprint.route('/download/<path:file>', methods=['GET'])
def download_log(file):
    """
    Download a specific log file.
    """
    log_path = os.path.join(LOG_DIR, file)
    if not os.path.exists(log_path):
        return jsonify({"status": "failure", "message": "File not found"}), 404
    return send_file(log_path, as_attachment=True)


# NEW: API Endpoint: Delete a specific log file
@log_blueprint.route('/delete/<path:file>', methods=['POST'])
def delete_log(file):
    """
    Delete a specific log file.
    """
    log_path = os.path.join(LOG_DIR, file)
    if not os.path.exists(log_path):
        return jsonify({"status": "failure", "message": "File not found"}), 404
    try:
        os.remove(log_path)
        return jsonify({"status": "success", "message": "File deleted"})
    except Exception as e:
        return jsonify({"status": "failure", "message": str(e)}), 500

# Note: The /add endpoint is deprecated, as logging is now handled automatically via log_service.py.
# If manual addition is still needed in the future, it can be re-added using log_event from log_service.