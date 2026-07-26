# File: services/log_service.py
import json
import os
from datetime import datetime, timedelta
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

# Define the log directory
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')

# Keep this much history in the local JSONL logs; the daily prune deletes the rest.
LOG_RETENTION_DAYS = 14
PRUNE_INTERVAL_SECONDS = 24 * 3600

def ensure_log_dir_exists():
    """
    Ensures the log directory exists.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

def _prune_decision(line, cutoff_iso):
    """
    Decide the fate of one JSONL line. Returns the line to write (cleaned), or
    None to drop it.

    NUL bytes injected by an unclean shutdown are stripped first: they are not
    data, and leaving them in makes the whole file read as binary and hides the
    entry's real timestamp. A line that still will not parse is kept - we cannot
    prove it is old, and silently dropping unreadable data is worse than size.
    """
    cleaned = line.replace('\x00', '').strip()
    if not cleaned:
        return None
    try:
        entry = json.loads(cleaned)
    except Exception:
        return cleaned
    ts = entry.get('timestamp')
    if not isinstance(ts, str):
        return cleaned
    return cleaned if ts >= cutoff_iso else None

def prune_log_file(log_file, days=LOG_RETENTION_DAYS):
    """
    Rewrite a JSONL log keeping only entries from the last `days` days.
    Returns (kept, removed). Writes to a temp file and atomically replaces the
    original, so a crash mid-prune cannot leave a truncated log.
    """
    if not os.path.isfile(log_file):
        return (0, 0)

    cutoff_iso = (datetime.now() - timedelta(days=days)).isoformat()
    tmp_file = log_file + '.prune_tmp'
    kept = removed = 0
    changed = False

    try:
        with open(log_file, 'r', errors='replace') as src, open(tmp_file, 'w') as dst:
            for line in src:
                if not line.strip():
                    changed = True
                    continue
                keep = _prune_decision(line, cutoff_iso)
                if keep is None:
                    removed += 1
                    changed = True
                else:
                    dst.write(keep + '\n')
                    kept += 1
                    if keep + '\n' != line:
                        changed = True
        if changed:
            os.replace(tmp_file, log_file)
        else:
            os.remove(tmp_file)
    except Exception as e:
        print(f"[LOG] Failed to prune {log_file}: {e}")
        try:
            os.remove(tmp_file)
        except Exception:
            pass
        return (kept, 0)

    return (kept, removed)

def prune_all_logs(days=LOG_RETENTION_DAYS):
    """Prune every *_log.jsonl in the log directory."""
    ensure_log_dir_exists()
    results = {}
    for name in sorted(os.listdir(LOG_DIR)):
        if not name.endswith('_log.jsonl'):
            continue
        kept, removed = prune_log_file(os.path.join(LOG_DIR, name), days)
        results[name] = (kept, removed)
        if removed:
            print(f"[LOG] Pruned {name}: removed {removed} entries older than {days} days, kept {kept}")
    return results

def prune_logs_daily():
    """Prune on startup, then once a day."""
    while True:
        try:
            prune_all_logs()
        except Exception as e:
            print(f"[LOG] Daily prune failed: {e}")
        time.sleep(PRUNE_INTERVAL_SECONDS)

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
        # Don't upload if not configured
        if not all([server_url, device_id, api_key]):
            return False

        # Convert WebSocket URL to HTTP URL for API calls
        server_url = server_url.replace('wss://', 'https://').replace('ws://', 'http://')
        # Remove /ws/devices path if present
        server_url = server_url.replace('/ws/devices', '')

        # Upload to server (no plant_id needed - server associates logs with all assigned plants)
        url = f"{server_url}/api/devices/{device_id}/logs?api_key={api_key}"
        response = requests.post(
            url,
            json=[log_entry],
            timeout=5
        )

        if response.status_code != 200:
            print(f"Failed to upload log: {response.status_code} - {response.text}")
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

    # Add phase from plant_info if available
    from utils.settings_utils import load_settings
    settings = load_settings()
    plant_info = settings.get('plant_info', {})
    if plant_info:
        # Get phase from plant_info, default to 'flower' if not set
        data_dict['phase'] = plant_info.get('phase', 'flower')

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
    log_event({
        'event_type': 'dosing',
        'sensor_name': 'ph',  # For consistency
        'value': ph,  # pH reading at time of dose
        'dose_type': dose_type,
        'dose_amount_ml': dose_amount_ml
    }, category='dosing')

def log_sensor_reading(sensor_name, value, additional_data=None):
    data = {
        'event_type': 'sensor',
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

def log_ec_periodically():
    """Log EC readings every 6 hours, similar to pH."""
    from services.ec_service import get_latest_ec_reading
    while True:
        ec = get_latest_ec_reading()
        if ec is not None:
            log_sensor_reading('ec', ec)
        time.sleep(6 * 3600)  # 6 hours in seconds

def upload_specific_log_file(filename):
    """
    Upload a specific log file to the server.
    """
    try:
        settings = get_cached_settings()
        server_url = settings.get("server_url")
        device_id = settings.get("device_id")
        api_key = settings.get("api_key")

        # Don't upload if not configured
        if not all([server_url, device_id, api_key]):
            print("Log upload skipped: server not configured")
            return False

        # Convert WebSocket URL to HTTP URL for API calls
        server_url = server_url.replace('wss://', 'https://').replace('ws://', 'http://')
        # Remove /ws/devices path if present
        server_url = server_url.replace('/ws/devices', '')

        log_file_path = os.path.join(LOG_DIR, filename)

        if not os.path.exists(log_file_path):
            print(f"Log file {filename} not found")
            return False

        # Read all log entries from file
        log_entries = []
        with open(log_file_path, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        log_entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        print(f"Skipping invalid JSON line in {filename}")
                        continue

        if not log_entries:
            print(f"No log entries found in {filename}")
            return False

        # Upload in batches of 100
        batch_size = 100
        total_uploaded = 0

        for i in range(0, len(log_entries), batch_size):
            batch = log_entries[i:i + batch_size]

            try:
                # No plant_id needed - server associates logs with all assigned plants
                url = f"{server_url}/api/devices/{device_id}/logs?api_key={api_key}"
                response = requests.post(
                    url,
                    json=batch,
                    timeout=30
                )

                if response.status_code == 200:
                    total_uploaded += len(batch)
                else:
                    print(f"Failed to upload batch from {filename}: {response.status_code}")
                    print(f"Response body: {response.text}")
                    return False

            except Exception as e:
                print(f"Error uploading batch from {filename}: {e}")
                return False

        # If all batches uploaded successfully, delete the local file
        # COMMENTED OUT FOR TESTING
        # try:
        #     os.remove(log_file_path)
        #     print(f"Deleted {filename} after successful upload ({total_uploaded} entries)")
        # except Exception as e:
        #     print(f"Failed to delete {filename}: {e}")
        print(f"Upload successful ({total_uploaded} entries). NOT deleting {filename} (deletion commented out for testing)")

        return True

    except Exception as e:
        print(f"Error in upload_specific_log_file: {e}")
        return False

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

        # Don't upload if not configured
        if not all([server_url, device_id, api_key]):
            print("Log upload skipped: server not configured")
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
                    # No plant_id needed - server associates logs with all assigned plants
                    url = f"{server_url}/api/devices/{device_id}/logs?api_key={api_key}"
                    response = requests.post(
                        url,
                        json=batch,
                        timeout=30
                    )

                    if response.status_code == 200:
                        total_uploaded += len(batch)
                    else:
                        print(f"Failed to upload batch: {response.status_code}")
                        print(f"Response body: {response.text}")
                        return False  # Stop on first failure

                except Exception as e:
                    print(f"Error uploading batch: {e}")
                    return False

            # If all batches uploaded successfully, delete the local file
            # COMMENTED OUT FOR TESTING
            # try:
            #     os.remove(log_file_path)
            #     print(f"Deleted {log_filename} after successful upload")
            # except Exception as e:
            #     print(f"Failed to delete {log_filename}: {e}")
            print(f"Upload successful. NOT deleting {log_filename} (deletion commented out for testing)")

        print(f"Successfully uploaded {total_uploaded} log entries")
        return True

    except Exception as e:
        print(f"Error in upload_pending_logs: {e}")
        return False

def sync_logs_background():
    """
    Background thread that periodically checks for and uploads pending logs.
    Syncs on boot, then every hour.
    """
    # Brief delay on startup to let services initialize
    time.sleep(30)

    while True:
        try:
            settings = get_cached_settings()
            server_enabled = settings.get("server_enabled", False)

            # Only sync if server is configured
            if server_enabled:
                print("Running background log sync...")
                upload_pending_logs()
        except Exception as e:
            print(f"Error in background log sync: {e}")

        time.sleep(3600)  # Sleep for 1 hour before next sync

# Start the periodic logging in a background thread
threading.Thread(target=log_ph_periodically, daemon=True).start()
threading.Thread(target=log_ec_periodically, daemon=True).start()

# Start the background log sync service
threading.Thread(target=sync_logs_background, daemon=True).start()

# Prune local logs on boot and once a day thereafter
threading.Thread(target=prune_logs_daily, daemon=True).start()