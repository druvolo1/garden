import threading
import time
import requests
from datetime import datetime

# Import your new helper
from utils.network_utils import standardize_host_ip
from utils.settings_utils import load_settings
from services.valve_relay_service import turn_off_valve as turn_off_valve_local
from services.valve_relay_service import turn_on_valve as turn_on_valve_local

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
    print("RPi.GPIO not available. Using mock environment.")

from utils.settings_utils import load_settings
from status_namespace import is_debug_enabled


_pins_lock = threading.Lock()
_pins_inited = False
_last_sensor_state = {}

def log_water_level(msg):
    """Logs messages only if debugging is enabled for water_level_service."""
    if is_debug_enabled("water_level_service"): 
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def load_water_level_sensors():
    s = load_settings()
    default_sensors = {
        "sensor1": {"label": "Full",  "pin": 17},
        "sensor2": {"label": "3 Gal", "pin": 18},
        "sensor3": {"label": "Empty", "pin": 19},
    }
    return s.get("water_level_sensors", default_sensors)


def ensure_pins_inited():
    global _pins_inited
    if not GPIO:
        log_water_level("[WaterLevel DEBUG] Mock environment, no GPIO setup.")
        return

    with _pins_lock:
        if not _pins_inited:
            try:
                GPIO.setwarnings(False)
                GPIO.setmode(GPIO.BCM)
                sensors = load_water_level_sensors()
                for sensor_key, cfg in sensors.items():
                    pin = cfg.get("pin")
                    if pin is not None:
                        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                _pins_inited = True
            except Exception as e:
                log_water_level(f"[WaterLevel DEBUG] Error initializing water-level pins: {e}")


def force_cleanup_and_init():
    if not GPIO:
        return

    with _pins_lock:
        global _pins_inited
        GPIO.cleanup()
        _pins_inited = False
        ensure_pins_inited()

def turn_off_fill_valve():
    """
    Checks settings to see if fill_valve is 'local' or 'remote',
    then calls the correct approach.
    """
    settings = load_settings()
    fill_mode = settings.get("fill_valve_mode", "local")  # or "remote"
    fill_valve_id_str = settings.get("fill_valve")        # e.g. "1"
    fill_valve_label  = settings.get("fill_valve_label")  # e.g. "Fill 4"
    fill_ip           = settings.get("fill_valve_ip", "")

    if fill_mode == "local":
        # Use the local approach
        if not fill_valve_id_str:
            print("[ERROR] fill_valve is not set, can't turn off locally.")
            return
        try:
            numeric_id = int(fill_valve_id_str)
            print(f"[DEBUG] Turning OFF fill valve locally, valve_id={numeric_id}")
            turn_off_valve_local(numeric_id)
        except Exception as ex:
            print(f"[ERROR] turn_off_fill_valve local failed: {ex}")
    else:
        # Remote approach: see if we have fill_valve_ip
        if not fill_ip:
            print("[ERROR] fill_valve_mode=remote but no fill_valve_ip is configured.")
            return
        final_ip = standardize_host_ip(fill_ip)
        if final_ip:
            fill_ip = final_ip
        if not fill_valve_label:
            fill_valve_label = "FillValve"
        # Call the remote API to turn off
        url = f"http://{fill_ip}:8000/api/valve_relay/{fill_valve_label}/off"
        try:
            resp = requests.post(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    print(f"[DEBUG] Fill valve OFF success (remote).")
                    # Request a status update from the remote to refresh REMOTE_STATES
                    status_url = f"http://{fill_ip}:8000/api/settings"
                    status_resp = requests.get(status_url)
                    if status_resp.status_code == 200:
                        status_data = status_resp.json()
                        from status_namespace import REMOTE_STATES
                        REMOTE_STATES[fill_ip] = status_data  # Update REMOTE_STATES directly
                        from status_namespace import emit_status_update
                        emit_status_update(force_emit=True)  # Force broadcast
                    else:
                        print(f"[ERROR] Failed to fetch status update from {fill_ip}: HTTP {status_resp.status_code}")
                else:
                    print(f"[ERROR] Fill valve OFF remote error: {data.get('error')}")
            else:
                print(f"[ERROR] Fill valve OFF returned HTTP {resp.status_code}")
        except Exception as ex:
            print(f"[ERROR] Remote fill valve OFF failed: {ex}")

def turn_on_fill_valve():
    """
    Checks settings to see if fill_valve is 'local' or 'remote',
    then calls the correct approach to turn it ON.
    """
    settings = load_settings()
    fill_mode = settings.get("fill_valve_mode", "local")  # or "remote"
    fill_valve_id_str = settings.get("fill_valve")        # e.g. "1"
    fill_valve_label  = settings.get("fill_valve_label")  # e.g. "Fill 4"
    fill_ip           = settings.get("fill_valve_ip", "")

    if fill_mode == "local":
        # Use the local approach
        if not fill_valve_id_str:
            print("[ERROR] fill_valve is not set, can't turn on locally.")
            return
        try:
            numeric_id = int(fill_valve_id_str)
            print(f"[DEBUG] Turning ON fill valve locally, valve_id={numeric_id}")
            turn_on_valve_local(numeric_id)
        except Exception as ex:
            print(f"[ERROR] turn_on_fill_valve local failed: {ex}")
    else:
        # Remote approach: see if we have fill_valve_ip
        if not fill_ip:
            print("[ERROR] fill_valve_mode=remote but no fill_valve_ip is configured.")
            return
        final_ip = standardize_host_ip(fill_ip)
        if final_ip:
            fill_ip = final_ip
        if not fill_valve_label:
            fill_valve_label = "FillValve"
        # Call the remote API to turn on
        url = f"http://{fill_ip}:8000/api/valve_relay/{fill_valve_label}/on"
        try:
            resp = requests.post(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    print(f"[DEBUG] Fill valve ON success (remote).")
                    # Request a status update from the remote to refresh REMOTE_STATES
                    status_url = f"http://{fill_ip}:8000/api/settings"
                    status_resp = requests.get(status_url)
                    if status_resp.status_code == 200:
                        status_data = status_resp.json()
                        from status_namespace import REMOTE_STATES
                        REMOTE_STATES[fill_ip] = status_data  # Update REMOTE_STATES directly
                        from status_namespace import emit_status_update
                        emit_status_update(force_emit=True)  # Force broadcast
                    else:
                        print(f"[ERROR] Failed to fetch status update from {fill_ip}: HTTP {status_resp.status_code}")
                else:
                    print(f"[ERROR] Fill valve ON remote error: {data.get('error')}")
            else:
                print(f"[ERROR] Fill valve ON returned HTTP {resp.status_code}")
        except Exception as ex:
            print(f"[ERROR] Remote fill valve ON failed: {ex}")

def turn_off_drain_valve():
    """
    Exactly the same pattern, but for drain_valve_mode, drain_valve_ip, etc.
    """
    settings = load_settings()
    drain_mode = settings.get("drain_valve_mode", "local")
    drain_valve_id_str = settings.get("drain_valve")
    drain_valve_label  = settings.get("drain_valve_label", "")
    drain_ip           = settings.get("drain_valve_ip", "")

    if drain_mode == "local":
        if not drain_valve_id_str:
            print("[ERROR] drain_valve is not set, can't turn off locally.")
            return
        try:
            numeric_id = int(drain_valve_id_str)
            print(f"[DEBUG] Turning OFF drain valve locally, valve_id={numeric_id}")
            turn_off_valve_local(numeric_id)
        except Exception as ex:
            print(f"[ERROR] turn_off_drain_valve local failed: {ex}")
    else:
        # Remote approach
        if not drain_ip:
            print("[ERROR] drain_valve_mode=remote but no drain_valve_ip is configured.")
            return
        final_ip = standardize_host_ip(drain_ip)
        if final_ip:
            drain_ip = final_ip
        if not drain_valve_label:
            drain_valve_label = "DrainValve"
        url = f"http://{drain_ip}:8000/api/valve_relay/{drain_valve_label}/off"
        try:
            resp = requests.post(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    print(f"[DEBUG] Drain valve OFF success (remote).")
                    # Request a status update from the remote to refresh REMOTE_STATES
                    status_url = f"http://{drain_ip}:8000/api/settings"
                    status_resp = requests.get(status_url)
                    if status_resp.status_code == 200:
                        status_data = status_resp.json()
                        from status_namespace import REMOTE_STATES
                        REMOTE_STATES[drain_ip] = status_data  # Update REMOTE_STATES directly
                        from status_namespace import emit_status_update
                        emit_status_update(force_emit=True)  # Force broadcast
                    else:
                        print(f"[ERROR] Failed to fetch status update from {drain_ip}: HTTP {status_resp.status_code}")
                else:
                    print(f"[ERROR] Drain valve OFF remote error: {data.get('error')}")
            else:
                print(f"[ERROR] Drain valve OFF returned HTTP {resp.status_code}")
        except Exception as ex:
            print(f"[ERROR] Remote drain valve OFF failed: {ex}")

def turn_off_valve(valve_label: str, valve_ip: str):
    """
    Calls /api/valve_relay/<valve_label>/off on the given IP (resolved by standardize_host_ip).
    """
    if not valve_label:
        print("[ERROR] No valve_label provided.")
        return
    if not valve_ip:
        print("[ERROR] No valve_ip provided (empty). Aborting turn_off_valve call.")
        return

    final_ip = standardize_host_ip(valve_ip)
    if final_ip:
        print(f"[DEBUG] Using resolved IP for valve control: '{final_ip}'.")
        valve_ip = final_ip

    url = f"http://{valve_ip}:8000/api/valve_relay/{valve_label}/off"

    try:
        resp = requests.post(url)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                print(f"Valve '{valve_label}' turned off successfully (http {valve_ip}).")
                # Request a status update from the remote to refresh REMOTE_STATES
                status_url = f"http://{valve_ip}:8000/api/settings"
                status_resp = requests.get(status_url)
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    from status_namespace import REMOTE_STATES
                    REMOTE_STATES[valve_ip] = status_data  # Update REMOTE_STATES directly
                    from status_namespace import emit_status_update
                    emit_status_update(force_emit=True)  # Force broadcast
                else:
                    print(f"[ERROR] Failed to fetch status update from {valve_ip}: HTTP {status_resp.status_code}")
            else:
                print(f"[ERROR] Valve '{valve_label}' off failed: {data.get('error')}")
        else:
            print(f"[ERROR] Valve '{valve_label}' off returned HTTP {resp.status_code}")
    except Exception as ex:
        print(f"[ERROR] Exception calling valve off route for '{valve_label}' on {valve_ip}: {ex}")

def get_water_level_status():
    sensors = load_water_level_sensors()
    ensure_pins_inited()

    log_water_level("[WaterLevel] Fetching sensor states...")

    status = {}
    if GPIO:
        for sensor_key, cfg in sensors.items():
            label = cfg.get("label", sensor_key)
            pin = cfg.get("pin")
            triggered = False
            if pin is not None:
                sensor_state = GPIO.input(pin)
                triggered = (sensor_state == 1)  # Inverted for NC: low (0) = triggered, (1) is no water / 'Not Present'
                log_water_level(f"[WaterLevel] Sensor {sensor_key} ({label}) pin {pin} state {sensor_state} triggered {triggered}")
            status[sensor_key] = {
                "label": label,
                "pin": pin,
                "triggered": triggered
            }
    else:
        # Mock environment: assume all sensors are "not triggered"
        for sensor_key, cfg in sensors.items():
            log_water_level(f"[WaterLevel] Mock sensor {sensor_key} ({cfg.get('label', sensor_key)}) triggered False")
            status[sensor_key] = {
                "label": cfg.get("label", sensor_key),
                "pin": cfg.get("pin"),
                "triggered": False
            }

    return status

import api.settings
from services.notification_service import _send_telegram_and_discord

def monitor_water_level_sensors():
    global _last_sensor_state
    while True:
        current_state = get_water_level_status()
        log_water_level(f"[WaterLevel] Current state: {current_state}")
        if current_state != _last_sensor_state:
            previous_state = _last_sensor_state
            _last_sensor_state = current_state
            settings = load_settings()

            fill_sensor_key  = settings.get("fill_sensor",  "sensor1")
            drain_sensor_key = settings.get("drain_sensor", "sensor3")
            auto_fill_key = settings.get("auto_fill_sensor", "disabled")

            log_water_level(f"[WaterLevel] State changed. Settings: fill_sensor={fill_sensor_key} drain_sensor={drain_sensor_key} auto_fill={auto_fill_key}")

            # For safety: always turn off fill if fill_sensor triggered
            if fill_sensor_key in current_state:
                fill_triggered = current_state[fill_sensor_key]["triggered"]
                log_water_level(f"[WaterLevel] Fill safety check: fill_triggered={fill_triggered}")
                if not fill_triggered:
                    log_water_level("[WaterLevel] Turning off fill due to full sensor")
                    turn_off_fill_valve()
                    #if not api.settings.feeding_in_progress:
                        #_send_telegram_and_discord("Auto filling is complete.")

            # For auto fill: if auto_fill_sensor not triggered, and not fill_triggered, turn on fill
            if auto_fill_key != "disabled" and auto_fill_key in current_state:
                auto_triggered = current_state[auto_fill_key]["triggered"]
                last_auto_triggered = previous_state.get(auto_fill_key, {"triggered": False})["triggered"]
                fill_triggered = current_state.get(fill_sensor_key, {"triggered": False})["triggered"]
                log_water_level(f"[WaterLevel] Auto fill check: auto_triggered={auto_triggered} last_auto_triggered={last_auto_triggered} fill_triggered={fill_triggered}")
                if not last_auto_triggered and auto_triggered and fill_triggered:
                    log_water_level(f"[WaterLevel] Checking feeding_in_progress value: {api.settings.feeding_in_progress}")
                    if not api.settings.feeding_in_progress:
                        log_water_level("[WaterLevel] Turning on fill for auto")
                        turn_on_fill_valve()
                        _send_telegram_and_discord("Auto filling was triggered.")
                    else:
                        log_water_level("[WaterLevel] Not turning on fill for auto because feeding is in progress")

            # If drain sensor is triggered => we want to turn off drain valve
            if drain_sensor_key in current_state:
                drain_triggered = current_state[drain_sensor_key]["triggered"]
                last_drain_triggered = previous_state.get(drain_sensor_key, {"triggered": False})["triggered"]
                log_water_level(f"[WaterLevel] Drain check: drain_triggered={drain_triggered}")
                if not last_drain_triggered and drain_triggered:
                    log_water_level("[WaterLevel] Turning off drain due to empty sensor")
                    turn_off_drain_valve()

            from status_namespace import emit_status_update
            emit_status_update()
        time.sleep(0.5)

def init_valve_thread():
    """
    Called from app.py startup to start the valve monitoring thread.
    """
    if not threading.current_thread() == threading.main_thread():
        print("[ERROR] init_valve_thread must be called from main thread.")
        return

    global _valve_thread
    _valve_thread = threading.Thread(target=monitor_valve_relays, daemon=True)
    _valve_thread.start()
    print("[DEBUG] Valve relay monitoring thread started.")

def stop_valve_thread():
    """
    Called when valve_relay device changes, to stop the monitoring thread.
    """
    global _valve_thread
    if '_valve_thread' in globals() and _valve_thread.is_alive():
        # Note: this is a bit dangerous; we should really have a clean shutdown
        # mechanism, but for now just let it die.
        print("[DEBUG] Attempting to stop valve relay monitoring thread.")
        _valve_thread = None  # This will allow the next init to start fresh

def monitor_valve_relays():
    """
    Polls the valve relay module every 0.5 seconds to check for changes.
    """
    settings = load_settings()
    valve_device = settings.get("usb_roles", {}).get("valve_relay")
    last_states = {}

    while True:
        if not valve_device:
            print("[DEBUG] No valve_relay device assigned, sleeping.")
            time.sleep(0.5)
            continue

        current_states = {}
        for i in range(1, 9):  # Assuming 8 relays
            status = get_valve_status(i)
            current_states[str(i)] = status

        if current_states != last_states:
            last_states = current_states
            from status_namespace import emit_status_update
            emit_status_update()

        time.sleep(0.5)

def get_valve_status(valve_id: int):
    """
    Fetch the current status of a valve from the relay module.
    Returns "on" or "off" as a string.
    """
    settings = load_settings()
    valve_device = settings.get("usb_roles", {}).get("valve_relay")

    if not valve_device:
        print(f"[DEBUG] No valve_relay device assigned, returning 'off' for valve {valve_id}")
        return "off"

    try:
        # Here you would typically query the hardware
        # For now, mock with a simple toggle based on time
        # Replace with actual hardware query when available
        current_time = time.time()
        # Mock toggle every 5 seconds for testing
        status = "on" if (current_time % 10) < 5 else "off"
        return status
    except Exception as e:
        print(f"[ERROR] Failed to get status for valve {valve_id}: {e}")
        return "off"

def turn_on_valve(valve_id: int):
    """
    Turn on a specific valve by its ID (1-8).
    """
    settings = load_settings()
    valve_device = settings.get("usb_roles", {}).get("valve_relay")

    if not valve_device:
        print(f"[ERROR] No valve_relay device assigned, can't turn on valve {valve_id}")
        return

    try:
        # Here you would send a command to the hardware
        print(f"[DEBUG] Turning ON valve {valve_id} (mock implementation)")
        # Mock implementation - replace with actual hardware command
    except Exception as e:
        print(f"[ERROR] Failed to turn on valve {valve_id}: {e}")

def turn_off_valve(valve_id: int):
    """
    Turn off a specific valve by its ID (1-8).
    """
    settings = load_settings()
    valve_device = settings.get("usb_roles", {}).get("valve_relay")

    if not valve_device:
        print(f"[ERROR] No valve_relay device assigned, can't turn off valve {valve_id}")
        return

    try:
        # Here you would send a command to the hardware
        print(f"[DEBUG] Turning OFF valve {valve_id} (mock implementation)")
        # Mock implementation - replace with actual hardware command
    except Exception as e:
        print(f"[ERROR] Failed to turn off valve {valve_id}: {e}")