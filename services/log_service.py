# File: services/log_service.py
import json
import os
from datetime import datetime
import threading
import time
from services.ph_service import get_latest_ph_reading
from utils.settings_utils import load_settings  # Import to access system_name

# Cache settings to avoid reloading on every log
_cached_settings = None

def get_cached_settings():
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = load_settings()
    return _cached_settings

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
    settings = get_cached_settings()
    plant = settings.get("system_name", "Unknown")
    
    log_event({
        'event_type': 'dosing',
        'plant': plant,  # Added
        'ph': ph,
        'dose_type': dose_type,
        'dose_amount_ml': dose_amount_ml
    }, category='dosing')

def log_sensor_reading(sensor_name, value, additional_data=None):
    settings = get_cached_settings()
    plant = settings.get("system_name", "Unknown")
    
    data = {
        'event_type': 'sensor',
        'plant': plant,  # Added
        'sensor_name': sensor_name,
        'value': value
    }
    if additional_data:
        data.update(additional_data)
    log_event(data, category=sensor_name)

def log_ph_periodically():
    while True:
        ph = get_latest_ph_reading()
        if ph is not None:
            log_sensor_reading('ph', ph)
        time.sleep(6 * 3600)  # 6 hours in seconds

# Start the periodic logging in a background thread
threading.Thread(target=log_ph_periodically, daemon=True).start()