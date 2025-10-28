# File: services/log_service.py
import json
import os
from datetime import datetime
import threading
import time
import requests
from services.ph_service import get_latest_ph_reading
from utils.settings_utils import load_settings  # Import to access system_name

# Cache settings to avoid reloading on every log
_cached_settings = None

def get_cached_settings():
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = load_settings()
    return _cached_settings

def reset_cache():
    global _cached_settings
    _cached_settings = None

# Define the log directory and file
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
SENSOR_LOG_FILE = os.path.join(LOG_DIR, 'sensor_log.jsonl')

def ensure_log_dir_exists():
    """
    Ensures the log directory exists.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

def upload_log_to_server(log_entry):
    """
    Upload a single log entry to the server.
    Returns True if successful, False otherwise.
    """
    try:
        settings = get_cached_settings()
        server_url = settings.get("server_url")
        device_id = settings.get("device_id")
        api_key = settings.get("api_key")
        plant_info = settings.get("plant_info", {})
        plant_id = plant_info.get("plant_id")

        # Don't upload if not configured or no active plant
        if not all([server_url, device_id, api_key, plant_id]):
            return False

        # Convert WebSocket URL to HTTP URL for API calls
        server_url = server_url.replace('wss://', 'https://').replace('ws://', 'http://')
        # Remove /ws/devices path if present
        server_url = server_url.replace('/ws/devices', '')

        # Upload to server
        url = f"{server_url}/api/devices/{device_id}/logs?api_key={api_key}&plant_id={plant_id}"
        response = requests.post(
            url,
            json=[log_entry],
            timeout=5
        )

        return response.status_code == 200

    except Exception as e:
        print(f"Failed to upload log to server: {e}")
        return False

def log_event(data_dict, category='sensor'):
    """
    Log an event. Try to upload to server first, fallback to local file if fails.
    """
    ensure_log_dir_exists()
    data_dict['timestamp'] = datetime.now().isoformat()

    # Try to upload to server
    uploaded = upload_log_to_server(data_dict)

    # If upload failed, write to local file as fallback
    if not uploaded:
        log_file = os.path.join(LOG_DIR, f'{category}_log.jsonl')
        with open(log_file, 'a') as f:
            f.write(json.dumps(data_dict) + '\n')

def log_dosing_event(ph, dose_type, dose_amount_ml):
    """
    Logs a dosing event (as a specific type of sensor event).
    """
    settings = get_cached_settings()
    system_id = settings.get("system_name", "Unknown")
    plant_name = settings.get("plant_info", {}).get("name", "Unknown")
    
    log_event({
        'event_type': 'dosing',
        'system_id': system_id,  # Added: Fixed system/zone
        'plant_name': plant_name,  # Added: Rotating variety
        'ph': ph,
        'dose_type': dose_type,
        'dose_amount_ml': dose_amount_ml
    }, category='dosing')

def log_sensor_reading(sensor_name, value, additional_data=None):
    settings = get_cached_settings()
    system_id = settings.get("system_name", "Unknown")
    plant_name = settings.get("plant_info", {}).get("name", "Unknown")
    
    data = {
        'event_type': 'sensor',
        'system_id': system_id,  # Added: Fixed system/zone
        'plant_name': plant_name,  # Added: Rotating variety
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

def upload_pending_logs():
    """
    Upload all pending logs from local JSONL files to the server.
    Called when finishing a plant or periodically in background.
    """
    try:
        settings = get_cached_settings()
        server_url = settings.get("server_url")
        device_id = settings.get("device_id")
        api_key = settings.get("api_key")
        plant_info = settings.get("plant_info", {})
        plant_id = plant_info.get("plant_id")

        # Don't upload if not configured or no active plant
        if not all([server_url, device_id, api_key, plant_id]):
            print("Log upload skipped: server not configured or no active plant")
            return False

        # Convert WebSocket URL to HTTP URL for API calls
        server_url = server_url.replace('wss://', 'https://').replace('ws://', 'http://')
        # Remove /ws/devices path if present
        server_url = server_url.replace('/ws/devices', '')

        # Read and upload logs from each file
        log_files = ['ph_log.jsonl', 'dosing_log.jsonl']
        total_uploaded = 0

        for log_filename in log_files:
            log_file_path = os.path.join(LOG_DIR, log_filename)

            if not os.path.exists(log_file_path):
                continue

            # Read all log entries from file
            log_entries = []
            with open(log_file_path, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            log_entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            print(f"Skipping invalid JSON line in {log_filename}")
                            continue

            if not log_entries:
                continue

            # Upload in batches of 100
            batch_size = 100
            for i in range(0, len(log_entries), batch_size):
                batch = log_entries[i:i + batch_size]

                try:
                    url = f"{server_url}/api/devices/{device_id}/logs?api_key={api_key}&plant_id={plant_id}"
                    response = requests.post(
                        url,
                        json=batch,
                        timeout=30
                    )

                    if response.status_code == 200:
                        total_uploaded += len(batch)
                    else:
                        print(f"Failed to upload batch: {response.status_code}")
                        return False  # Stop on first failure

                except Exception as e:
                    print(f"Error uploading batch: {e}")
                    return False

            # If all batches uploaded successfully, delete the local file
            try:
                os.remove(log_file_path)
                print(f"Deleted {log_filename} after successful upload")
            except Exception as e:
                print(f"Failed to delete {log_filename}: {e}")

        print(f"Successfully uploaded {total_uploaded} log entries")
        return True

    except Exception as e:
        print(f"Error in upload_pending_logs: {e}")
        return False

def sync_logs_background():
    """
    Background thread that periodically checks for and uploads pending logs.
    Runs every hour.
    """
    while True:
        time.sleep(3600)  # Sleep for 1 hour

        try:
            settings = get_cached_settings()
            plant_info = settings.get("plant_info", {})

            # Only sync if there's an active plant
            if plant_info.get("plant_id"):
                print("Running background log sync...")
                upload_pending_logs()
        except Exception as e:
            print(f"Error in background log sync: {e}")

# Start the periodic logging in a background thread
threading.Thread(target=log_ph_periodically, daemon=True).start()

# Start the background log sync service
threading.Thread(target=sync_logs_background, daemon=True).start()