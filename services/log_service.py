# File: services/log_service.py
import json
import os
from datetime import datetime

# Define the log directory and file
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
SENSOR_LOG_FILE = os.path.join(LOG_DIR, 'sensor_log.jsonl')

def ensure_log_dir_exists():
    """
    Ensures the log directory exists.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

def log_event(data_dict):
    """
    Logs an event as a JSON object on a new line in the JSONL file.
    Always includes 'timestamp'; add sensor keys/values as needed.
    Example: log_event({'ph': 7.2, 'dose_type': 'up', 'dose_amount_ml': 5.0})
    """
    ensure_log_dir_exists()
    data_dict['timestamp'] = datetime.now().isoformat()
    with open(SENSOR_LOG_FILE, 'a') as f:
        f.write(json.dumps(data_dict) + '\n')

def log_dosing_event(ph, dose_type, dose_amount_ml):
    """
    Logs a dosing event (as a specific type of sensor event).
    """
    log_event({
        'event_type': 'dosing',
        'ph': ph,
        'dose_type': dose_type,
        'dose_amount_ml': dose_amount_ml
    })

# Future: Log other sensors
# def log_sensor_reading(sensor_name, value, additional_data=None):
#     data = {'event_type': 'sensor', 'sensor_name': sensor_name, 'value': value}
#     if additional_data:
#         data.update(additional_data)
#     log_event(data)