from flask import Blueprint, jsonify, request
import os
import json
from datetime import datetime

# Create the Blueprint for logs
log_blueprint = Blueprint('logs', __name__)

# Path to the logs file
LOGS_FILE = os.path.join(os.getcwd(), "data", "logs", "dosage_log.json")

# Ensure the logs directory exists
os.makedirs(os.path.dirname(LOGS_FILE), exist_ok=True)

# Ensure the logs file exists
if not os.path.exists(LOGS_FILE):
    with open(LOGS_FILE, "w") as f:
        json.dump([], f)


# Helper function: Load logs from file
def load_logs():
    with open(LOGS_FILE, "r") as f:
        return json.load(f)


# Helper function: Save logs to file
def save_logs(logs):
    with open(LOGS_FILE, "w") as f:
        json.dump(logs, f, indent=4)


# API Endpoint: Get all logs
@log_blueprint.route('/', methods=['GET'])
def get_logs():
    """
    Retrieve all dosage logs.
    """
    logs = load_logs()
    return jsonify(logs)


# API Endpoint: Add a new log entry
@log_blueprint.route('/add', methods=['POST'])
def add_log():
    """
    Add a new log entry. Expects JSON payload with log details.
    """
    new_log = request.json
    logs = load_logs()

    # Add timestamp to the new log entry
    new_log["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Add the new log entry to the logs
    logs.append(new_log)
    save_logs(logs)

    return jsonify({"status": "success", "log": new_log})


# API Endpoint: Clear all logs
@log_blueprint.route('/clear', methods=['POST'])
def clear_logs():
    """
    Clear all dosage logs.
    """
    save_logs([])
    return jsonify({"status": "success", "message": "Logs cleared."})
