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

def log_event(data_dict, category='sensor'):
    log_file = os.path.join(LOG_DIR, f'{category}_log.jsonl')
    ensure_log_dir_exists()
    data_dict['timestamp'] = datetime.now().isoformat()
    with open(log_file, 'a') as f:
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
    }, category='dosing')

# Future: Log other sensors
# def log_sensor_reading(sensor_name, value, additional_data=None):
#     data = {'event_type': 'sensor', 'sensor_name': sensor_name, 'value': value}
#     if additional_data:
#         data.update(additional_data)
#     log_event(data)